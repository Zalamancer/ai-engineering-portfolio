"""Slow-drift detection (guide Phase 4.3): a moving average of pass rate over the last N runs of
the same prompt version dropping below a threshold, even when no single run tripped an alert."""
from __future__ import annotations

import statistics


def detect_drift(history: list[dict], window: int, threshold: float) -> dict:
    """history: run summaries, newest first, same prompt version (baseline + candidates alike)."""
    rates = [r["pass_rate"] for r in history if r.get("pass_rate") is not None][:window]
    if len(rates) < window:
        return {"drift": False, "reason": f"need {window} runs, have {len(rates)}", "window": window, "moving_average": None,
                "threshold": threshold, "runs_used": [r["run_id"] for r in history[:len(rates)]]}
    ma = statistics.mean(rates)
    return {"drift": ma < threshold, "moving_average": round(ma, 4), "threshold": threshold, "window": window,
            "runs_used": [r["run_id"] for r in history[:window]],
            "reason": (f"{window}-run moving average {ma:.3f} below {threshold}" if ma < threshold else
                       f"{window}-run moving average {ma:.3f} at or above {threshold}")}
