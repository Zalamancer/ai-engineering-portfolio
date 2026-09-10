"""Diffing (guide Phase 3.3–3.4). Two separate things are reported and named:
1. POLICY verdict: pass-rate delta vs the 3 % / 8 % configurable thresholds (warn / critical).
2. STATISTICS: how many cases flipped each way, an exact McNemar-style binomial test on the
   discordant pairs (p-value), and 95 % Wilson intervals on both pass rates — so '2 of 80 flipped'
   can be read as signal or noise. Small samples give wide intervals; that is reported, not hidden.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from scipy.stats import binomtest


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


@dataclass
class Flip:
    case_id: str
    expected_category: str
    difficulty: str
    baseline_output: str | None
    candidate_output: str | None
    baseline_category: str | None
    candidate_category: str | None
    baseline_summary_score: int | None
    candidate_summary_score: int | None
    reason: str


@dataclass
class Comparison:
    baseline_run_id: str
    candidate_run_id: str
    n_common: int
    baseline_pass_rate: float
    candidate_pass_rate: float
    pass_rate_delta: float
    category_accuracy_delta: float | None
    per_category_accuracy_delta: dict
    regressions: list[Flip]
    improvements: list[Flip]
    verdict: str                       # pass | warn | critical
    verdict_basis: str
    stats: dict = field(default_factory=dict)
    same_dataset: bool = True
    dataset_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _reason(b: dict, c: dict) -> str:
    parts = []
    if b["category_correct"] and not c["category_correct"]:
        parts.append(f"category {b['predicted_category']}→{c['predicted_category'] or 'INVALID'}")
    if b["output_valid"] and not c["output_valid"]:
        parts.append(f"output invalid: {c['validation_error']}")
    if b["summary_pass"] and not c["summary_pass"]:
        parts.append(f"summary score {b['summary_score']}→{c['summary_score']}")
    if not parts:
        parts.append("improved" if c["passed"] and not b["passed"] else "changed")
    return "; ".join(parts)


def compare(base_meta: dict, base_cases: dict[str, dict], cand_meta: dict, cand_cases: dict[str, dict],
            warn_delta: float, critical_delta: float) -> Comparison:
    common = sorted(set(base_cases) & set(cand_cases))
    n = len(common)
    b_pass = sum(1 for cid in common if base_cases[cid]["passed"])
    c_pass = sum(1 for cid in common if cand_cases[cid]["passed"])
    b_rate = b_pass / n if n else 0.0
    c_rate = c_pass / n if n else 0.0
    delta = c_rate - b_rate
    regressions = [Flip(cid, base_cases[cid]["expected_category"], base_cases[cid]["difficulty"], base_cases[cid]["raw_output"],
                        cand_cases[cid]["raw_output"], base_cases[cid]["predicted_category"], cand_cases[cid]["predicted_category"],
                        base_cases[cid]["summary_score"], cand_cases[cid]["summary_score"], _reason(base_cases[cid], cand_cases[cid]))
                   for cid in common if base_cases[cid]["passed"] and not cand_cases[cid]["passed"]]
    improvements = [Flip(cid, base_cases[cid]["expected_category"], base_cases[cid]["difficulty"], base_cases[cid]["raw_output"],
                         cand_cases[cid]["raw_output"], base_cases[cid]["predicted_category"], cand_cases[cid]["predicted_category"],
                         base_cases[cid]["summary_score"], cand_cases[cid]["summary_score"], "fail → pass")
                    for cid in common if not base_cases[cid]["passed"] and cand_cases[cid]["passed"]]

    cats = sorted({base_cases[c]["expected_category"] for c in common})
    per_cat = {}
    for cat in cats:
        ids = [c for c in common if base_cases[c]["expected_category"] == cat]
        ba = sum(base_cases[c]["category_correct"] for c in ids) / len(ids)
        ca = sum(cand_cases[c]["category_correct"] for c in ids) / len(ids)
        per_cat[cat] = {"n": len(ids), "baseline": round(ba, 4), "candidate": round(ca, 4), "delta": round(ca - ba, 4)}
    b_acc = sum(base_cases[c]["category_correct"] for c in common) / n if n else None
    c_acc = sum(cand_cases[c]["category_correct"] for c in common) / n if n else None

    # --- policy verdict (thresholds are configurable policy, not a significance test) ------
    drop = -delta
    if drop > critical_delta:
        verdict, basis = "critical", f"pass rate dropped {100 * drop:.1f} pp > critical threshold {100 * critical_delta:.0f} pp"
    elif drop > warn_delta:
        verdict, basis = "warn", f"pass rate dropped {100 * drop:.1f} pp > warning threshold {100 * warn_delta:.0f} pp"
    else:
        verdict, basis = "pass", f"pass rate change {100 * delta:+.1f} pp within warning threshold {100 * warn_delta:.0f} pp"

    # --- statistics on the discordant pairs (exact McNemar / two-sided binomial) -------------
    b_only, c_only = len(regressions), len(improvements)
    disc = b_only + c_only
    p_value = binomtest(b_only, disc, 0.5).pvalue if disc else None
    stats = {
        "n": n, "flipped_to_fail": b_only, "flipped_to_pass": c_only, "discordant_pairs": disc,
        "mcnemar_exact_p_value": round(p_value, 4) if p_value is not None else None,
        "baseline_pass_rate_wilson95": wilson(b_pass, n), "candidate_pass_rate_wilson95": wilson(c_pass, n),
        "reading": ("no discordant pairs" if not disc else
                    f"{b_only} regressions vs {c_only} improvements among {disc} flipped cases; exact two-sided p={p_value:.3f}. "
                    + ("This is consistent with noise at n=%d." % n if p_value > 0.05 else "Unlikely to be noise at the 5 %% level (n=%d)." % n)),
        "caveat": "With fewer than ~100 cases, differences under ~8-10 pp are rarely statistically distinguishable; the policy thresholds are a product decision, not a test.",
    }
    same = base_meta.get("dataset_fingerprint") == cand_meta.get("dataset_fingerprint")
    note = "" if same else (f"dataset changed between runs ({base_meta.get('dataset_version')} {base_meta.get('dataset_fingerprint')} → "
                            f"{cand_meta.get('dataset_version')} {cand_meta.get('dataset_fingerprint')}); only the {n} common case ids are compared")
    return Comparison(base_meta["run_id"], cand_meta["run_id"], n, round(b_rate, 4), round(c_rate, 4), round(delta, 4),
                      round(c_acc - b_acc, 4) if b_acc is not None else None, per_cat, regressions, improvements,
                      verdict, basis, stats, same, note)
