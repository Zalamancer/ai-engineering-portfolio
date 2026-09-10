"""Test runner (guide Phase 3.1): runs every golden case through the feature with bounded
concurrency, scores each, aggregates. Latency percentiles and token totals are recorded."""
from __future__ import annotations

import asyncio
import statistics
import time

from .config import Settings
from .dataset import GoldenCase, GoldenDataset
from .feature import Classifier, PromptConfig
from .scoring import CaseScore, Judge, score_case


def _pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p / 100 * (len(xs) - 1))))
    return round(xs[k], 1)


async def _run_all(cases: list[GoldenCase], cfg: PromptConfig, clf: Classifier, judge: Judge | None,
                   settings: Settings, log=print) -> list[CaseScore]:
    sem = asyncio.Semaphore(settings.concurrency)
    results: dict[str, CaseScore] = {}

    async def one(i: int, case: GoldenCase):
        async with sem:
            res = await asyncio.to_thread(clf.classify, case.input, cfg)
            sc = await asyncio.to_thread(score_case, case, res, judge, settings.summary_pass_score)
            results[case.id] = sc
            log(f"[{i}/{len(cases)}] {case.id} {case.expected_category:>9} → {sc.predicted_category or 'INVALID':<9} "
                f"cat={'ok' if sc.category_correct else 'X '} sum={sc.summary_score} {'PASS' if sc.passed else 'FAIL'} {sc.latency_ms:.0f}ms")

    await asyncio.gather(*(one(i, c) for i, c in enumerate(cases, 1)))
    return [results[c.id] for c in cases]


def run_eval(cfg: PromptConfig, dataset: GoldenDataset, settings: Settings, run_id: str, only_verified: bool = False,
             log=print, clf: Classifier | None = None, judge: Judge | None | bool = True) -> tuple[dict, list[CaseScore]]:
    cases = dataset.active(only_verified=only_verified)
    clf = clf or Classifier(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_s)
    if judge is True:
        judge = Judge(settings.llm_base_url, settings.llm_api_key, settings.judge_model or settings.llm_model, settings.llm_timeout_s)
    t0 = time.time()
    scores = asyncio.run(_run_all(cases, cfg, clf, judge or None, settings, log))
    meta = aggregate(scores, cfg, dataset, settings, run_id, only_verified)
    meta.update({"model": cfg.model or settings.llm_model, "judge_model": (settings.judge_model or settings.llm_model) if judge else None,
                 "wall_seconds": round(time.time() - t0, 1)})
    return meta, scores


def aggregate(scores: list[CaseScore], cfg: PromptConfig, dataset: GoldenDataset, settings: Settings, run_id: str,
              only_verified: bool) -> dict:
    n = len(scores)
    lat = [s.latency_ms for s in scores]
    by_cat: dict[str, dict] = {}
    for s in scores:
        d = by_cat.setdefault(s.expected_category, {"n": 0, "correct": 0, "passed": 0})
        d["n"] += 1
        d["correct"] += int(s.category_correct)
        d["passed"] += int(s.passed)
    for d in by_cat.values():
        d["accuracy"] = round(d["correct"] / d["n"], 4) if d["n"] else None
        d["pass_rate"] = round(d["passed"] / d["n"], 4) if d["n"] else None
    by_diff: dict[str, dict] = {}
    for s in scores:
        d = by_diff.setdefault(s.difficulty, {"n": 0, "passed": 0})
        d["n"] += 1
        d["passed"] += int(s.passed)
    for d in by_diff.values():
        d["pass_rate"] = round(d["passed"] / d["n"], 4) if d["n"] else None
    verified = sum(1 for c in dataset.active(only_verified) if c.verification.status == "human_verified")
    return {
        "run_id": run_id, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "prompt_version": cfg.version,
        "prompt_path": getattr(cfg, "_path", None), "dataset_version": dataset.version, "dataset_fingerprint": dataset.fingerprint(),
        "n_cases": n, "n_verified": verified, "only_verified": only_verified,
        "dataset_label": "human-verified" if verified == n and n > 0 else f"{verified}/{n} human-verified; rest AI-drafted",
        "pass_rate": round(sum(s.passed for s in scores) / n, 4) if n else None,
        "category_accuracy": round(sum(s.category_correct for s in scores) / n, 4) if n else None,
        "summary_pass_rate": round(sum(s.summary_pass for s in scores) / n, 4) if n else None,
        "summary_score_mean": round(statistics.mean([s.summary_score for s in scores if s.summary_score]), 3) if any(s.summary_score for s in scores) else None,
        "output_valid_rate": round(sum(s.output_valid for s in scores) / n, 4) if n else None,
        "latency_p50_ms": _pct(lat, 50), "latency_p95_ms": _pct(lat, 95), "latency_mean_ms": round(statistics.mean(lat), 1) if lat else None,
        "prompt_tokens": sum(s.prompt_tokens or 0 for s in scores) if any(s.prompt_tokens for s in scores) else None,
        "completion_tokens": sum(s.completion_tokens or 0 for s in scores) if any(s.completion_tokens for s in scores) else None,
        "by_category": by_cat, "by_difficulty": by_diff, "status": "candidate", "baseline_run_id": None, "notes": "",
        "thresholds": {"warn_delta": settings.warn_delta, "critical_delta": settings.critical_delta,
                       "summary_pass_score": settings.summary_pass_score, "kind": "policy thresholds, not statistical significance"},
    }
