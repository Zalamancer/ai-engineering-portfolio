"""Command line.

  uv run regress run --prompt prompts/v1.yaml --set-baseline      # first run becomes the baseline
  uv run regress run --prompt prompts/v2.yaml [--gate] [--send]    # compare with the latest baseline
  uv run regress compare <baseline_run_id> <candidate_run_id>
  uv run regress history
  uv run regress dataset-stats
  uv run regress confidence-curve <run_id>      # jev runs: accuracy vs coverage at confidence thresholds
  uv run regress versus <run_a> <run_b>         # cross-backend comparison (LLM vs jev): accuracy, latency, tokens, cost
Exit codes: 0 pass/warn, 2 critical regression (when --gate), 3 invalid configuration.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .alerts import build_slack_message, deliver
from .compare import compare
from .config import settings
from .dataset import GoldenDataset
from .drift import detect_drift
from .feature import CATEGORIES, PromptConfig
from .report import render_report
from .runner import run_eval
from .storage import Store, new_run_id


def _finish(store: Store, cand_meta: dict, cand_cases: dict, base_meta: dict | None, args) -> int:
    comparison = None
    if base_meta:
        comparison = compare(base_meta, store.get_cases(base_meta["run_id"]), cand_meta, cand_cases,
                             settings.warn_delta, settings.critical_delta).to_dict()
        cand_meta["baseline_run_id"] = base_meta["run_id"]
        cand_meta["verdict"] = comparison["verdict"]
    history = store.list_runs(limit=50, prompt_version=cand_meta["prompt_version"])
    drift = detect_drift(history, settings.drift_window, settings.drift_threshold)
    cand_meta["drift"] = drift
    store.save_run(cand_meta, list(cand_cases.values()))
    report = render_report(cand_meta, cand_cases, comparison, drift, history[:20], settings.reports_dir / f"{cand_meta['run_id']}.html", base_meta)
    (settings.runs_dir / cand_meta["run_id"] / "comparison.json").write_text(json.dumps(comparison, indent=1, default=str) if comparison else "null")
    report_url = f"{settings.report_base_url.rstrip('/')}/{report.name}" if settings.report_base_url else None
    payload = build_slack_message(cand_meta, comparison, drift, report_url)
    delivery = deliver(payload, settings.slack_webhook_url, getattr(args, "send", False), settings.runs_dir.parent / "alerts" / "outbox")
    print(f"\nrun {cand_meta['run_id']}: pass rate {cand_meta['pass_rate']} · category acc {cand_meta['category_accuracy']} · "
          f"valid {cand_meta['output_valid_rate']} · p50 {cand_meta['latency_p50_ms']} ms · dataset {cand_meta['dataset_label']}")
    if comparison:
        print(f"vs baseline {base_meta['run_id']}: {comparison['verdict'].upper()} — {comparison['verdict_basis']}; "
              f"{len(comparison['regressions'])} regressions, {len(comparison['improvements'])} improvements; {comparison['stats']['reading']}")
    print(f"drift: {drift['reason']}")
    print(f"report: {report}\nslack: {delivery['status']} (payload saved to {delivery['saved_to']})")
    if getattr(args, "gate", False) and comparison and comparison["verdict"] == "critical":
        print("GATE: critical regression — failing", file=sys.stderr)
        return 2
    return 0


def cmd_run(args) -> int:
    try:
        cfg = PromptConfig.load(args.prompt)
        if args.model:
            cfg.model = args.model      # model swap under the same prompt (e.g. jev-latest → jev-preview)
        if args.no_temperature:
            cfg.temperature = None
        ds = GoldenDataset.load(Path(args.golden) if args.golden else settings.golden_path)
    except Exception as e:
        print(f"invalid configuration: {e}", file=sys.stderr)
        return 3
    store = Store(settings.db_path, settings.runs_dir)
    run_id = new_run_id(cfg.version + (f"-{args.tag}" if args.tag else f"-{args.model}" if args.model else "") + ("-holdout" if args.golden else ""))
    default_model = settings.jev_model if cfg.backend == "jev" else settings.llm_model
    print(f"prompt {cfg.version} · backend {cfg.backend} · dataset {ds.version} ({ds.counts()['by_status']}) · model {cfg.model or default_model}")
    meta, scores = run_eval(cfg, ds, settings, run_id, only_verified=args.only_verified, judge=not args.no_judge)
    cases = {s.case_id: s.to_dict() for s in scores}
    base = None
    if args.set_baseline:
        meta["status"] = "baseline"
    elif args.golden and not args.baseline:
        print("custom dataset: not compared against the stored baseline (pass --baseline <run_id> to diff two runs on it)", file=sys.stderr)
    else:
        base = store.get_run(args.baseline) if args.baseline else store.latest_baseline(cfg.backend)
        if not base:
            print(f"no {cfg.backend} baseline yet — run once with --set-baseline", file=sys.stderr)
    return _finish(store, meta, cases, base, args)


def cmd_compare(args) -> int:
    store = Store(settings.db_path, settings.runs_dir)
    b, c = store.get_run(args.baseline), store.get_run(args.candidate)
    if not b or not c:
        print("unknown run id", file=sys.stderr)
        return 3
    cmp = compare(b, store.get_cases(b["run_id"]), c, store.get_cases(c["run_id"]), settings.warn_delta, settings.critical_delta)
    print(json.dumps({k: v for k, v in cmp.to_dict().items() if k not in ("regressions", "improvements")}, indent=1))
    print(f"regressions: {[r.case_id for r in cmp.regressions]}\nimprovements: {[r.case_id for r in cmp.improvements]}")
    return 2 if args.gate and cmp.verdict == "critical" else 0


def cmd_history(args) -> int:
    store = Store(settings.db_path, settings.runs_dir)
    for r in store.list_runs(limit=args.limit):
        print(f"{r['run_id']:<32} {r.get('backend', 'openai'):<6} {r['status']:<9} pass={r['pass_rate']} acc={r['category_accuracy']} valid={r['output_valid_rate']} "
              f"p50={r['latency_p50_ms']}ms dataset={r['dataset_version']}/{r['dataset_fingerprint']} verdict={r.get('verdict', '-')}")
    return 0


def cmd_dataset_stats(args) -> int:
    ds = GoldenDataset.load(settings.golden_path)
    print(json.dumps({"version": ds.version, "fingerprint": ds.fingerprint(), **ds.counts()}, indent=1))
    return 0


JEV_USD_PER_MTOK_INPUT = 0.042   # docs.typesafe.ai/models, 2026-09-20; output tokens are free


def confidence_curve(cases: dict[str, dict], thresholds=(0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95)) -> list[dict]:
    """Confidence-gated routing (TypeSafe pattern): at threshold t the classifier acts only when
    confidence >= t and sends the rest to a human. Reports coverage and accuracy on the acted-on part."""
    rows = []
    scored = [c for c in cases.values() if c.get("confidence") is not None]
    for t in thresholds:
        acted = [c for c in scored if c["confidence"] >= t]
        correct = sum(1 for c in acted if c["category_correct"])
        rows.append({"threshold": t, "n_acted": len(acted), "coverage": round(len(acted) / len(scored), 4) if scored else None,
                     "accuracy_when_acting": round(correct / len(acted), 4) if acted else None,
                     "routed_to_human": len(scored) - len(acted),
                     "wrong_and_acted": len(acted) - correct})
    return rows


def cmd_confidence_curve(args) -> int:
    store = Store(settings.db_path, settings.runs_dir)
    meta, cases = store.get_run(args.run_id), store.get_cases(args.run_id)
    if not meta:
        print("unknown run id", file=sys.stderr)
        return 3
    if not any(c.get("confidence") is not None for c in cases.values()):
        print("this run has no confidence values (only the jev backend reports them)", file=sys.stderr)
        return 3
    rows = confidence_curve(cases)
    print(f"run {args.run_id} · {meta['model']} · mean confidence {meta.get('confidence_mean')} "
          f"(correct {meta.get('confidence_mean_correct')} / wrong {meta.get('confidence_mean_wrong')})")
    print(f"{'threshold':>9} {'acted':>6} {'coverage':>9} {'accuracy':>9} {'to human':>9} {'wrong&acted':>12}")
    for r in rows:
        print(f"{r['threshold']:>9.2f} {r['n_acted']:>6} {100 * r['coverage']:>8.1f}% {100 * (r['accuracy_when_acting'] or 0):>8.1f}% "
              f"{r['routed_to_human']:>9} {r['wrong_and_acted']:>12}")
    if args.json:
        print(json.dumps(rows, indent=1))
    return 0


def versus(a_meta: dict, a_cases: dict, b_meta: dict, b_cases: dict) -> dict:
    """Side-by-side of two runs on the *category* dimension, which both backends share. Pass rate is
    not compared here because the LLM's pass rate includes the summary judge and jev has no summary."""
    common = sorted(set(a_cases) & set(b_cases))

    def side(meta, cases):
        n = len(common)
        acc = sum(1 for cid in common if cases[cid]["category_correct"]) / n if n else None
        by_cat = {cat: {"n": 0, "correct": 0} for cat in CATEGORIES}
        for cid in common:
            c = cases[cid]
            by_cat[c["expected_category"]]["n"] += 1
            by_cat[c["expected_category"]]["correct"] += int(c["category_correct"])
        toks_in = meta.get("prompt_tokens")
        cost = round(toks_in / 1e6 * JEV_USD_PER_MTOK_INPUT / n * 1000, 4) if (meta.get("backend") == "jev" and toks_in and n) else None
        return {"run_id": meta["run_id"], "backend": meta.get("backend", "openai"), "model": meta["model"],
                "category_accuracy": round(acc, 4) if acc is not None else None,
                "per_category": {k: round(v["correct"] / v["n"], 4) if v["n"] else None for k, v in by_cat.items()},
                "latency_p50_ms": meta.get("latency_p50_ms"), "latency_p95_ms": meta.get("latency_p95_ms"),
                "wall_seconds": meta.get("wall_seconds"), "prompt_tokens": toks_in, "completion_tokens": meta.get("completion_tokens"),
                "usd_per_1k_emails": cost, "confidence_mean": meta.get("confidence_mean")}
    a, b = side(a_meta, a_cases), side(b_meta, b_cases)
    flips = {"a_right_b_wrong": [cid for cid in common if a_cases[cid]["category_correct"] and not b_cases[cid]["category_correct"]],
             "b_right_a_wrong": [cid for cid in common if b_cases[cid]["category_correct"] and not a_cases[cid]["category_correct"]],
             "both_wrong": [cid for cid in common if not a_cases[cid]["category_correct"] and not b_cases[cid]["category_correct"]]}
    same = a_meta.get("dataset_fingerprint") == b_meta.get("dataset_fingerprint")
    return {"n_common": len(common), "same_dataset": same, "a": a, "b": b, "flips": flips}


def cmd_versus(args) -> int:
    store = Store(settings.db_path, settings.runs_dir)
    a, b = store.get_run(args.run_a), store.get_run(args.run_b)
    if not a or not b:
        print("unknown run id", file=sys.stderr)
        return 3
    v = versus(a, store.get_cases(a["run_id"]), b, store.get_cases(b["run_id"]))
    if args.json:
        print(json.dumps(v, indent=1))
        return 0
    A, B = v["a"], v["b"]
    print(f"{v['n_common']} common cases · same dataset fingerprint: {v['same_dataset']}")
    print(f"{'':<22} {'A: ' + A['run_id']:<34} {'B: ' + B['run_id']:<34}")
    print(f"{'backend / model':<22} {A['backend'] + ' / ' + str(A['model']):<34} {B['backend'] + ' / ' + str(B['model']):<34}")
    fmt = lambda x, f: "–" if x is None else f.format(x)
    print(f"{'category accuracy':<22} {fmt(A['category_accuracy'], '{:.1%}'):<34} {fmt(B['category_accuracy'], '{:.1%}'):<34}")
    for cat in CATEGORIES:
        print(f"{'  ' + cat:<22} {fmt(A['per_category'][cat], '{:.1%}'):<34} {fmt(B['per_category'][cat], '{:.1%}'):<34}")
    print(f"{'latency p50 / p95':<22} {fmt(A['latency_p50_ms'], '{:.0f} ms') + ' / ' + fmt(A['latency_p95_ms'], '{:.0f} ms'):<34} "
          f"{fmt(B['latency_p50_ms'], '{:.0f} ms') + ' / ' + fmt(B['latency_p95_ms'], '{:.0f} ms'):<34}")
    print(f"{'wall clock (80 cases)':<22} {fmt(A['wall_seconds'], '{:.1f} s'):<34} {fmt(B['wall_seconds'], '{:.1f} s'):<34}")
    print(f"{'input / output tokens':<22} {str(A['prompt_tokens']) + ' / ' + str(A['completion_tokens']):<34} {str(B['prompt_tokens']) + ' / ' + str(B['completion_tokens']):<34}")
    print(f"{'USD per 1k emails':<22} {fmt(A['usd_per_1k_emails'], '${:.4f}'):<34} {fmt(B['usd_per_1k_emails'], '${:.4f}'):<34}")
    print(f"{'mean confidence':<22} {fmt(A['confidence_mean'], '{:.3f}'):<34} {fmt(B['confidence_mean'], '{:.3f}'):<34}")
    f = v["flips"]
    print(f"A right / B wrong: {f['a_right_b_wrong']}\nB right / A wrong: {f['b_right_a_wrong']}\nboth wrong: {f['both_wrong']}")
    return 0


def cmd_set_baseline(args) -> int:
    Store(settings.db_path, settings.runs_dir).mark_baseline(args.run_id)
    print("baseline =", args.run_id)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="regress")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--prompt", required=True); r.add_argument("--baseline"); r.add_argument("--set-baseline", action="store_true")
    r.add_argument("--gate", action="store_true"); r.add_argument("--send", action="store_true", help="actually POST to Slack (needs REG_SLACK_WEBHOOK_URL)")
    r.add_argument("--only-verified", action="store_true", help="score only human-verified cases")
    r.add_argument("--model", help="override the prompt's model for this run (e.g. jev-preview)")
    r.add_argument("--no-judge", action="store_true", help="skip the summary judge: pass = category correct ∧ output valid")
    r.add_argument("--no-temperature", action="store_true", help="omit the temperature parameter (models that reject it)")
    r.add_argument("--tag", help="suffix for the run id (e.g. the provider name)")
    r.add_argument("--golden", help="score a different dataset file (e.g. a held-out set); no automatic baseline comparison")
    c = sub.add_parser("compare"); c.add_argument("baseline"); c.add_argument("candidate"); c.add_argument("--gate", action="store_true")
    h = sub.add_parser("history"); h.add_argument("--limit", type=int, default=20)
    sub.add_parser("dataset-stats")
    b = sub.add_parser("set-baseline"); b.add_argument("run_id")
    cc = sub.add_parser("confidence-curve"); cc.add_argument("run_id"); cc.add_argument("--json", action="store_true")
    vs = sub.add_parser("versus"); vs.add_argument("run_a"); vs.add_argument("run_b"); vs.add_argument("--json", action="store_true")
    args = ap.parse_args()
    sys.exit({"run": cmd_run, "compare": cmd_compare, "history": cmd_history, "dataset-stats": cmd_dataset_stats, "set-baseline": cmd_set_baseline,
              "confidence-curve": cmd_confidence_curve, "versus": cmd_versus}[args.cmd](args))
