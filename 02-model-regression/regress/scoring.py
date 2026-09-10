"""Multi-dimensional scoring (guide Phase 3.2): category match, summary quality (LLM judge 1-5),
output validity, latency, tokens. Judge scores are model judgments and are labelled as such."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from openai import OpenAI

from .dataset import GoldenCase
from .feature import FeatureResult

JUDGE_PROMPT = """You are grading a one-sentence summary of a customer support email.

EMAIL:
\"\"\"{email}\"\"\"

REFERENCE SUMMARY (written by a person): {reference}

CANDIDATE SUMMARY: {candidate}

Score the CANDIDATE from 1 to 5 for how well it captures the customer's actual issue and request compared with the REFERENCE:
5 = captures the same issue and request, accurate
4 = captures the issue, minor detail missing or extra
3 = partially right, misses an important part or adds something not in the email
2 = mostly wrong or vague
1 = wrong, empty, or not a summary

Reply with just the digit."""


@dataclass
class CaseScore:
    case_id: str
    expected_category: str
    predicted_category: str | None
    category_correct: bool
    output_valid: bool
    validation_error: str | None
    summary_score: int | None            # 1-5 from the judge (None if invalid output)
    summary_pass: bool
    passed: bool                         # category_correct AND output_valid AND summary_pass
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    raw_output: str
    predicted_summary: str | None
    difficulty: str
    judge_raw: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Judge:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120.0):
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=1)
        self.model = model

    def score_summary(self, email: str, reference: str, candidate: str) -> tuple[int | None, str]:
        try:
            resp = self.client.chat.completions.create(
                model=self.model, temperature=0.0, max_tokens=4,
                messages=[{"role": "user", "content": JUDGE_PROMPT.format(email=email, reference=reference, candidate=candidate)}])
            text = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return None, f"judge error: {type(e).__name__}"
        m = re.search(r"[1-5]", text)
        return (int(m.group()) if m else None), text


def score_case(case: GoldenCase, res: FeatureResult, judge: Judge | None, summary_pass_score: int) -> CaseScore:
    valid = res.parsed is not None
    pred_cat = res.parsed.category if valid else None
    pred_sum = res.parsed.summary if valid else None
    cat_ok = valid and pred_cat == case.expected_category
    s_score, j_raw = (None, None)
    if valid and judge is not None:
        s_score, j_raw = judge.score_summary(case.input, case.expected_summary, pred_sum or "")
    # no judge configured → summary is "not judged" and does not block a pass (recorded as None)
    s_pass = (s_score is not None and s_score >= summary_pass_score) if judge is not None else valid
    return CaseScore(
        case_id=case.id, expected_category=case.expected_category, predicted_category=pred_cat,
        category_correct=bool(cat_ok), output_valid=valid, validation_error=res.validation_error,
        summary_score=s_score, summary_pass=s_pass, passed=bool(cat_ok and valid and s_pass),
        latency_ms=res.latency_ms, prompt_tokens=res.prompt_tokens, completion_tokens=res.completion_tokens,
        raw_output=res.raw_output, predicted_summary=pred_sum, difficulty=case.expected_difficulty, judge_raw=j_raw,
    )
