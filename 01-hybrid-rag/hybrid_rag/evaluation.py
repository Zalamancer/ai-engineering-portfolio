"""Evaluation primitives: gold-evidence matching for retrieval, LLM-as-judge for answers.

All judge outputs are produced by the configured LLM (by default the same local 4B
model) and are labelled as such in results — they are model judgments, not human ones.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .generation import Answer, build_context

_WS = re.compile(r"\s+")


def norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def load_questions(path: Path, split: str | None = None, types: set[str] | None = None) -> list[dict]:
    data = json.loads(path.read_text())
    qs = data["questions"]
    if split and split != "all":
        qs = [q for q in qs if q["split"] == split]
    if types:
        qs = [q for q in qs if q["type"] in types]
    return qs


# ---------------------------------------------------------------------------------------
# Retrieval metrics: does any retrieved chunk contain the gold evidence quote?
# ---------------------------------------------------------------------------------------
def evidence_hits(question: dict, hit_texts: list[tuple[str, str]]) -> list[int | None]:
    """For each evidence item return the 1-based rank of the first chunk (same doc) that
    contains the quote, or None."""
    out: list[int | None] = []
    for ev in question.get("evidence", []):
        q = norm(ev["quote"])
        rank = None
        for i, (doc_id, text) in enumerate(hit_texts, start=1):
            if doc_id == ev["doc_id"] and q in norm(text):
                rank = i
                break
        out.append(rank)
    return out


def retrieval_metrics(ranks: list[int | None]) -> dict:
    found = [r for r in ranks if r is not None]
    return {
        "hit": 1.0 if found else 0.0,                          # at least one evidence passage retrieved
        "evidence_recall": len(found) / len(ranks) if ranks else 0.0,
        "all_found": 1.0 if ranks and len(found) == len(ranks) else 0.0,
        "mrr": (1.0 / min(found)) if found else 0.0,
    }


# ---------------------------------------------------------------------------------------
# Answer judgments
# ---------------------------------------------------------------------------------------
CORRECTNESS_PROMPT = """You are grading a documentation assistant's answer against a reference answer.

QUESTION: {question}

REFERENCE ANSWER (ground truth): {gold}

SYSTEM ANSWER: {answer}

Grade how correct and complete the SYSTEM ANSWER is relative to the REFERENCE, on this scale:
5 = fully correct and complete
4 = correct, minor omission or extra detail
3 = partially correct, missing an important part
2 = mostly wrong or misleading
1 = wrong or does not answer

Reply with just the digit."""

GROUNDED_PROMPT = """CONTEXT PASSAGES:
{context}

CLAIM: "{claim}"

Is the CLAIM supported by the CONTEXT PASSAGES (any of them)? Reply with exactly one word: SUPPORTED, PARTIAL, or NOT_SUPPORTED."""


def judge_correctness(llm, question: str, gold: str, answer: str) -> tuple[int | None, str]:
    resp = llm.chat([{"role": "user", "content": CORRECTNESS_PROMPT.format(question=question, gold=gold, answer=answer)}],
                    max_tokens=4, temperature=0.0)
    m = re.search(r"[1-5]", resp.text)
    return (int(m.group()) if m else None), resp.text.strip()


def judge_faithfulness(llm, ans: Answer, hits) -> dict:
    """Fraction of claims supported by the retrieved context (not just by the cited passage).
    Cited claims reuse the citation verdicts; uncited claims are judged against all passages."""
    if not ans.claims:
        return {"faithfulness": None, "n_claims": 0, "judged": []}
    context = build_context(hits)
    supported = 0
    judged = []
    for c in ans.claims:
        if c.supported:
            supported += 1
            judged.append({"claim": c.claim, "verdict": "SUPPORTED(cited)"})
            continue
        resp = llm.chat([{"role": "user", "content": GROUNDED_PROMPT.format(context=context, claim=c.claim)}],
                        max_tokens=6, temperature=0.0)
        w = resp.text.strip().upper()
        v = "SUPPORTED" if w.startswith("SUPPORTED") else "PARTIAL" if w.startswith("PARTIAL") else "NOT_SUPPORTED"
        if v == "SUPPORTED":
            supported += 1
        judged.append({"claim": c.claim, "verdict": v})
    return {"faithfulness": supported / len(ans.claims), "n_claims": len(ans.claims), "judged": judged}


def citation_accuracy(ans: Answer) -> dict:
    pairs = [(n, v) for c in ans.claims for n, v in c.verdicts.items()]
    if not pairs:
        return {"citation_precision": None, "n_citation_pairs": 0, "partial_rate": None}
    sup = sum(1 for _, v in pairs if v == "SUPPORTED")
    part = sum(1 for _, v in pairs if v == "PARTIAL")
    return {"citation_precision": sup / len(pairs), "n_citation_pairs": len(pairs), "partial_rate": part / len(pairs)}


def status_expectation(q: dict, ans: Answer) -> dict:
    """Did the system land in the right state for this question type?"""
    t = q["type"]
    text = ans.answer.lower()
    if t == "no_answer":
        ok = ans.status == "insufficient"
        return {"expected_status": "insufficient", "status_ok": ok, "hallucinated_answer": not ok}
    if t == "ambiguous":
        kws = [k.lower() for k in q.get("ambiguity_keywords", [])]
        mentioned = sum(1 for k in kws if k in text)
        ok = ans.status == "ambiguous" or mentioned >= 2
        return {"expected_status": "ambiguous", "status_ok": ok, "interpretations_mentioned": mentioned}
    ok = ans.status == "answered"
    return {"expected_status": "answered", "status_ok": ok, "wrongly_abstained": ans.status == "insufficient"}
