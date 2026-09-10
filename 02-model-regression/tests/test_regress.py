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
        assert cfg.version and cfg.system_prompt and cfg.created
        assert cfg.messages("hi")[-1] == {"role": "user", "content": "hi"}


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
