"""Command line.

  uv run regress run --prompt prompts/v1.yaml --set-baseline      # first run becomes the baseline
  uv run regress run --prompt prompts/v2.yaml [--gate] [--send]    # compare with the latest baseline
  uv run regress compare <baseline_run_id> <candidate_run_id>
  uv run regress history
  uv run regress dataset-stats
Exit codes: 0 pass/warn, 2 critical regression (when --gate), 3 invalid configuration.
"""
from __future__ import annotations

import argparse
import json
import sys

from .alerts import build_slack_message, deliver
from .compare import compare
from .config import settings
from .dataset import GoldenDataset
from .drift import detect_drift
from .feature import PromptConfig
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
        ds = GoldenDataset.load(settings.golden_path)
    except Exception as e:
        print(f"invalid configuration: {e}", file=sys.stderr)
        return 3
    store = Store(settings.db_path, settings.runs_dir)
    run_id = new_run_id(cfg.version)
    print(f"prompt {cfg.version} · dataset {ds.version} ({ds.counts()['by_status']}) · model {cfg.model or settings.llm_model}")
    meta, scores = run_eval(cfg, ds, settings, run_id, only_verified=args.only_verified)
    cases = {s.case_id: s.to_dict() for s in scores}
    base = None
    if args.set_baseline:
        meta["status"] = "baseline"
    else:
        base = store.get_run(args.baseline) if args.baseline else store.latest_baseline()
        if not base:
            print("no baseline yet — run once with --set-baseline", file=sys.stderr)
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
        print(f"{r['run_id']:<32} {r['status']:<9} pass={r['pass_rate']} acc={r['category_accuracy']} valid={r['output_valid_rate']} "
              f"p50={r['latency_p50_ms']}ms dataset={r['dataset_version']}/{r['dataset_fingerprint']} verdict={r.get('verdict', '-')}")
    return 0


def cmd_dataset_stats(args) -> int:
    ds = GoldenDataset.load(settings.golden_path)
    print(json.dumps({"version": ds.version, "fingerprint": ds.fingerprint(), **ds.counts()}, indent=1))
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
    c = sub.add_parser("compare"); c.add_argument("baseline"); c.add_argument("candidate"); c.add_argument("--gate", action="store_true")
    h = sub.add_parser("history"); h.add_argument("--limit", type=int, default=20)
    sub.add_parser("dataset-stats")
    b = sub.add_parser("set-baseline"); b.add_argument("run_id")
    args = ap.parse_args()
    sys.exit({"run": cmd_run, "compare": cmd_compare, "history": cmd_history, "dataset-stats": cmd_dataset_stats, "set-baseline": cmd_set_baseline}[args.cmd](args))
