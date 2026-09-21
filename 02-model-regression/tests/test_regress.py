import json
from pathlib import Path

import pytest

from regress.alerts import build_slack_message, deliver
from regress.compare import compare, wilson
from regress.config import Settings
from regress.dataset import GoldenDataset
from regress.drift import detect_drift
from regress.feature import FeatureResult, PromptConfig, parse_output
from regress.report import render_report
from regress.runner import run_eval
from regress.scoring import score_case
from regress.storage import Store

ROOT = Path(__file__).resolve().parent.parent


def test_prompt_configs_load_and_have_versions():
    for p in sorted((ROOT / "prompts").glob("*.yaml")):
        cfg = PromptConfig.load(p)
        assert cfg.version and cfg.created
        if cfg.backend == "openai":
            assert cfg.system_prompt
            assert cfg.messages("hi")[-1] == {"role": "user", "content": "hi"}
        else:
            q = cfg.jev_question()
            assert q["type"] == "choice" and set(q["criteria"]) == {"billing", "technical", "account", "general"}


def test_jev_prompt_config_is_validated():
    with pytest.raises(Exception):
        PromptConfig(version="x", created="2026-09-20T00:00:00", backend="jev", instructions="q", criteria={"billing": "a"})
    cfg = PromptConfig(version="x", created="2026-09-20T00:00:00", backend="jev", instructions={"question": "q"},
                       criteria={c: {"covers": c} for c in ("billing", "technical", "account", "general")}, state_context={"company": "acme"})
    assert cfg.jev_state("hi") == {"company": "acme", "email": "hi"}
    assert cfg.jev_question()["instructions"] == {"question": "q"}


def test_golden_dataset_schema_and_labels():
    ds = GoldenDataset.load(ROOT / "data" / "golden" / "golden.json")
    assert len(ds.cases) >= 50
    assert len({c.id for c in ds.cases}) == len(ds.cases)
    assert set(ds.counts()["by_category"]) == {"billing", "technical", "account", "general"}
    assert ds.fingerprint() and len(ds.fingerprint()) == 12
    # the draft must be honest about its provenance
    assert all(c.verification.status in {"ai_generated", "human_verified", "rejected"} for c in ds.cases)


@pytest.mark.parametrize("text,ok,cat", [
    ('{"category": "billing", "summary": "Customer wants a refund for a duplicate charge."}', True, "billing"),
    ('Sure! {"category": "Technical", "summary": "App crashes on launch on Android."}', True, "technical"),
    ('{"category": "refund", "summary": "x y z a b"}', False, None),
    ('{"category": "billing"}', False, None),
    ("I think this is about billing.", False, None),
    ('{"category": "general", "summary": "hi"}', False, None),
])
def test_parse_output_validates_schema(text, ok, cat):
    parsed, err = parse_output(text)
    assert (parsed is not None) == ok
    if ok:
        assert parsed.category == cat
    else:
        assert err


class FakeClassifier:
    """Deterministic stand-in: returns the expected label for ids in `right`, a wrong label otherwise."""
    def __init__(self, ds: GoldenDataset, right: set[str], invalid: set[str] = frozenset()):
        self.expected = {c.input: c for c in ds.cases}
        self.right, self.invalid = right, invalid

    def classify(self, email, cfg):
        c = self.expected[email]
        if c.id in self.invalid:
            return FeatureResult("oops not json", None, "no JSON object in output", 5.0, 10, 3, "fake")
        cat = c.expected_category if c.id in self.right else ("general" if c.expected_category != "general" else "billing")
        raw = json.dumps({"category": cat, "summary": c.expected_summary})
        parsed, _ = parse_output(raw)
        return FeatureResult(raw, parsed, None, 5.0, 100, 20, "fake")


def _settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "runs.db", runs_dir=tmp_path / "runs", reports_dir=tmp_path / "reports",
                    golden_path=ROOT / "data" / "golden" / "golden.json", slack_webhook_url="", drift_window=3)


def test_end_to_end_with_fake_model_detects_regression(tmp_path):
    s = _settings(tmp_path)
    ds = GoldenDataset.load(s.golden_path)
    cfg = PromptConfig.load(ROOT / "prompts" / "v1.yaml")
    ids = [c.id for c in ds.cases]
    store = Store(s.db_path, s.runs_dir)
    # baseline: all correct (judge disabled → summary scores None → summary_pass False, so scoring uses category+validity only here)
    base_meta, base_scores = run_eval(cfg, ds, s, "base", clf=FakeClassifier(ds, set(ids)), judge=None, log=lambda *_: None)
    base_meta["status"] = "baseline"
    store.save_run(base_meta, [x.to_dict() for x in base_scores])
    # candidate: 10 of 80 wrong, 2 invalid  → 15 pp drop → critical
    bad = set(ids[:10])
    cand_meta, cand_scores = run_eval(cfg, ds, s, "cand", clf=FakeClassifier(ds, set(ids) - bad, invalid=set(ids[10:12])), judge=None, log=lambda *_: None)
    store.save_run(cand_meta, [x.to_dict() for x in cand_scores])
    assert base_meta["category_accuracy"] == 1.0 and base_meta["pass_rate"] == 1.0
    assert cand_meta["output_valid_rate"] == pytest.approx(78 / 80) and cand_meta["pass_rate"] == pytest.approx(68 / 80)
    cmp = compare(base_meta, store.get_cases("base"), cand_meta, store.get_cases("cand"), s.warn_delta, s.critical_delta)
    # summary judge was off, so passed==False everywhere; compare on category flips via a judge-free pass definition
    assert cmp.n_common == 80 and cmp.category_accuracy_delta == pytest.approx(-12 / 80)
    assert cmp.verdict == "critical" and len(cmp.regressions) == 12 and cmp.stats["mcnemar_exact_p_value"] < 0.01
    # store + history + drift + report + alert payload
    hist = store.list_runs(prompt_version="v1")
    assert [h["run_id"] for h in hist] == ["cand", "base"]
    d = detect_drift(hist, window=3, threshold=0.9)
    assert d["drift"] is False and "need 3 runs" in d["reason"]
    out = render_report(cand_meta, store.get_cases("cand"), cmp.to_dict(), d, hist, tmp_path / "r.html", base_meta)
    html = out.read_text()
    assert "Regression report" in html and "<svg" in html and "c001" in html
    payload = build_slack_message(cand_meta, cmp.to_dict(), d, None)
    assert payload["blocks"] and "vs baseline" in payload["text"]
    res = deliver(payload, "", send=False, outbox=tmp_path / "outbox")
    assert res["delivered"] is False and "pending" in res["status"] and Path(res["saved_to"]).exists()


def test_policy_verdicts_and_statistics():
    def cases(passes):
        return {f"c{i}": {"passed": p, "category_correct": p, "output_valid": True, "summary_pass": p, "summary_score": 5 if p else 2,
                          "expected_category": "billing", "difficulty": "easy", "raw_output": "", "predicted_category": "billing",
                          "validation_error": None} for i, p in enumerate(passes)}
    base = {"run_id": "b", "dataset_fingerprint": "x"}
    cand = {"run_id": "c", "dataset_fingerprint": "x"}
    n = 100
    ok = compare(base, cases([True] * n), cand, cases([True] * 98 + [False] * 2), 0.03, 0.08)
    assert ok.verdict == "pass" and ok.stats["flipped_to_fail"] == 2 and ok.stats["mcnemar_exact_p_value"] == 0.5
    warn = compare(base, cases([True] * n), cand, cases([True] * 95 + [False] * 5), 0.03, 0.08)
    assert warn.verdict == "warn"
    crit = compare(base, cases([True] * n), cand, cases([True] * 90 + [False] * 10), 0.03, 0.08)
    assert crit.verdict == "critical" and crit.stats["mcnemar_exact_p_value"] < 0.01 and len(crit.regressions) == 10
    lo, hi = wilson(90, 100)
    assert lo < 0.9 < hi and hi - lo > 0.1  # a 100-case set still has a >10 pp wide interval


def test_drift_detection_fires_on_moving_average():
    hist = [{"run_id": f"r{i}", "pass_rate": r} for i, r in enumerate([0.84, 0.83, 0.85, 0.82, 0.86, 0.84, 0.85, 0.95])]
    d = detect_drift(hist, window=7, threshold=0.85)
    assert d["drift"] is True and d["moving_average"] < 0.85
    assert detect_drift(hist[-7:], window=7, threshold=0.85)["drift"] is False or detect_drift(hist, 7, 0.80)["drift"] is False


def test_bad_prompt_is_clearly_labelled():
    cfg = PromptConfig.load(ROOT / "prompts" / "v3-bad.yaml")
    assert "INTENTIONALLY BAD" in cfg.description


# ---------------------------------------------------------------------------------------------- jev backend

def _jev_transport(answer: dict, status: int = 200, usage=None):
    """Fake TypeSafe endpoint: records the request body, returns a canned Choice answer."""
    import httpx
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"models": [{"name": "jev-latest"}]})
        return httpx.Response(status, json={"model": "jev-1.13.0", "answers": {"category": answer},
                                            "usage": usage or {"input_tokens": 120, "output_tokens": 30}})
    return httpx.MockTransport(handler), seen


def test_jev_classifier_sends_one_choice_question_and_reads_typed_answer():
    from regress.feature import JevClassifier
    cfg = PromptConfig.load(ROOT / "prompts" / "jev-v1.yaml")
    transport, seen = _jev_transport({"type": "choice", "choice": "billing", "confidence": 0.9,
                                      "probabilities": {"billing": 0.93, "technical": 0.02, "account": 0.02, "general": 0.03}})
    clf = JevClassifier("test-key", transport=transport)
    res = clf.classify("charged twice, refund pls", cfg)
    body = seen[0]
    assert body["state"] == "charged twice, refund pls" and body["model"] == "jev-latest"
    assert list(body["questions"]) == ["category"] and body["questions"]["category"]["type"] == "choice"
    assert set(body["questions"]["category"]["criteria"]) == {"billing", "technical", "account", "general"}
    assert res.parsed and res.parsed.category == "billing" and res.parsed.summary is None
    assert res.confidence == 0.9 and res.probabilities["billing"] == 0.93
    assert res.prompt_tokens == 120 and res.completion_tokens == 30 and res.model == "jev-1.13.0"
    assert res.validation_error is None


def test_jev_classifier_records_failures_instead_of_crashing():
    from regress.feature import JevClassifier
    cfg = PromptConfig.load(ROOT / "prompts" / "jev-v1.yaml")
    transport, _ = _jev_transport({}, status=500)
    res = JevClassifier("test-key", transport=transport, max_retries=0).classify("x", cfg)
    assert res.parsed is None and res.validation_error.startswith("request failed")
    transport, _ = _jev_transport({"type": "choice", "choice": "refund"})   # not one of our options
    res = JevClassifier("test-key", transport=transport).classify("x", cfg)
    assert res.parsed is None and res.validation_error.startswith("schema")
    with pytest.raises(ValueError):
        JevClassifier("")


def test_jev_run_skips_judge_and_stores_confidence(tmp_path):
    """A jev run: pass = category correct ∧ valid (summary not applicable); confidence is aggregated,
    stored in SQLite (migrated columns) and drives the confidence-gated routing curve."""
    from regress.cli import confidence_curve, versus
    from regress.feature import JevClassifier
    ds = GoldenDataset.load(ROOT / "data" / "golden" / "golden.json")
    cfg = PromptConfig.load(ROOT / "prompts" / "jev-v1.yaml")
    expected = {c.input: c.expected_category for c in ds.cases}
    wrong = {c.id for c in ds.cases[:6]}
    by_input = {c.input: c.id for c in ds.cases}

    class FakeJev(JevClassifier):
        def __init__(self):
            pass

        def classify(self, email, cfg):
            cat = expected[email]
            if by_input[email] in wrong:
                cat = "general" if cat != "general" else "billing"
                conf = 0.2
            else:
                conf = 0.95
            return FeatureResult(json.dumps({"choice": cat}), __import__("regress.feature", fromlist=["Classification"]).Classification(category=cat),
                                 None, 80.0, 100, 20, "jev-1.13.0", confidence=conf, probabilities={cat: 0.9})
    settings = Settings(db_path=tmp_path / "r.db", runs_dir=tmp_path / "runs", reports_dir=tmp_path / "reports")
    meta, scores = run_eval(cfg, ds, settings, "t_jev", clf=FakeJev(), log=lambda *_: None)
    assert meta["backend"] == "jev" and meta["judge_model"] is None and meta["model"] == "jev-1.13.0"
    assert meta["pass_rate"] == meta["category_accuracy"] == round(74 / 80, 4)
    assert meta["confidence_mean_wrong"] == 0.2 and meta["confidence_mean_correct"] == 0.95
    store = Store(settings.db_path, settings.runs_dir)
    store.save_run(meta, [s.to_dict() for s in scores])
    cases = store.get_cases("t_jev")
    assert cases["c001"]["confidence"] == 0.2 and cases["c001"]["probabilities"] == {"general": 0.9}
    curve = confidence_curve(cases)
    assert curve[0]["coverage"] == 1.0 and curve[0]["accuracy_when_acting"] == round(74 / 80, 4)
    at_half = next(r for r in curve if r["threshold"] == 0.5)
    assert at_half["routed_to_human"] == 6 and at_half["accuracy_when_acting"] == 1.0
    # baselines are per backend: a jev candidate never diffs against an LLM baseline
    meta["status"] = "baseline"; store.save_run(meta, [s.to_dict() for s in scores])
    assert store.latest_baseline("jev")["run_id"] == "t_jev" and store.latest_baseline("openai") is None
    v = versus(meta, cases, meta, cases)
    assert v["n_common"] == 80 and v["a"]["usd_per_1k_emails"] == round(8000 / 1e6 * 0.042 / 80 * 1000, 4)
