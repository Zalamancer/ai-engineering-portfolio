"""Grounded generation, citation parsing, citation verification, confidence scoring and
the explicit 'insufficient evidence' / 'ambiguous question' paths (guide Phase 3)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .retrieval import Hit, RetrievalResult

SYSTEM_PROMPT = """You are a documentation assistant for an engineering team. Answer ONLY from the numbered context passages.

Rules:
1. Every factual sentence must end with the citation(s) of the passage(s) that support it, like [2] or [1][3]. Cite only passage numbers that exist.
2. Do not use any knowledge that is not in the passages. If the passages do not contain enough information, say so instead of guessing.
3. If the question could reasonably mean two different things given the passages (for example the same term used by two different tools), do not pick one silently: name the interpretations, answer each briefly if the passages allow, and say which one needs clarification.
4. Be concise: 1–5 sentences, plain prose, no headings.

Reply in exactly this format:
STATUS: <one of: answered | insufficient | ambiguous>
ANSWER:
<your answer>"""

VERIFY_PROMPT = """You are checking whether a citation is justified.

PASSAGE:
\"\"\"{passage}\"\"\"

CLAIM: "{claim}"

Does the PASSAGE support the CLAIM? Reply with exactly one word:
SUPPORTED (the passage states or directly implies the claim), PARTIAL (the passage supports some of the claim but not all of it), or NOT_SUPPORTED (the passage does not support the claim or contradicts it)."""

COMPLETENESS_PROMPT = """QUESTION: {question}

ANSWER: {answer}

Does the ANSWER address every part of the QUESTION? Ignore whether it is correct; judge only coverage.
Reply with exactly one word: FULL, PARTIAL, or NONE."""

_CITE_RE = re.compile(r"\[(\d{1,2})\]")
_STATUS_RE = re.compile(r"STATUS:\s*(answered|insufficient|ambiguous)", re.I)


def build_context(hits: list[Hit]) -> str:
    blocks = []
    for h in hits:
        c = h.chunk
        where = f"{c.doc_id} § {c.section}" + (f", page {c.page}" if c.page else "")
        blocks.append(f"[{h.rank}] ({where})\n{c.text}")
    return "\n\n".join(blocks)


def build_messages(question: str, hits: list[Hit]) -> list[dict]:
    user = f"CONTEXT PASSAGES:\n\n{build_context(hits)}\n\nQUESTION: {question}"
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse_generation(text: str) -> tuple[str, str]:
    """Returns (status, answer_text). Tolerates missing STATUS line."""
    m = _STATUS_RE.search(text)
    status = m.group(1).lower() if m else "answered"
    body = text
    if "ANSWER:" in text:
        body = text.split("ANSWER:", 1)[1]
    elif m:
        body = text[m.end():]
    body = re.sub(r"<think>.*?</think>", "", body, flags=re.S).strip()
    return status, body


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"'(\[])|(?<=[.!?]\])\s+(?=[A-Z`\"'(])")


def split_claims(answer: str) -> list[tuple[str, list[int]]]:
    """Sentence-level claims with the citation numbers attached to each."""
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(answer) if s.strip()]
    claims = []
    for s in sentences:
        cites = [int(n) for n in _CITE_RE.findall(s)]
        clean = re.sub(r"\s+([.,;:!?])", r"\1", _CITE_RE.sub("", s)).strip()
        if len(clean) < 3:
            continue
        claims.append((clean, sorted(set(cites))))
    return claims


@dataclass
class Citation:
    n: int
    chunk_id: str
    doc_id: str
    title: str
    section: str
    page: int | None
    source_url: str
    excerpt: str


@dataclass
class ClaimCheck:
    claim: str
    citations: list[int]
    verdicts: dict[int, str] = field(default_factory=dict)   # n -> SUPPORTED | PARTIAL | NOT_SUPPORTED | INVALID
    supported: bool = False


@dataclass
class Answer:
    question: str
    status: str                       # answered | insufficient | ambiguous
    answer: str
    citations: list[Citation]
    claims: list[ClaimCheck]
    confidence: dict
    flags: list[str]
    retrieval: dict
    model: str
    timings_ms: dict
    usage: dict
    not_found: dict | None = None     # populated for the 'insufficient' path

    def to_dict(self) -> dict:
        return asdict(self)


def verify_claims(llm, claims: list[tuple[str, list[int]]], hits_by_n: dict[int, Hit]) -> tuple[list[ClaimCheck], dict]:
    checks: list[ClaimCheck] = []
    n_calls = 0
    for claim, cites in claims:
        cc = ClaimCheck(claim=claim, citations=cites)
        for n in cites:
            if n not in hits_by_n:
                cc.verdicts[n] = "INVALID"      # cited a passage number that does not exist
                continue
            resp = llm.chat([{"role": "user", "content": VERIFY_PROMPT.format(passage=hits_by_n[n].chunk.text, claim=claim)}],
                            max_tokens=8, temperature=0.0)
            n_calls += 1
            word = resp.text.strip().upper()
            cc.verdicts[n] = "SUPPORTED" if word.startswith("SUPPORTED") else "PARTIAL" if word.startswith("PARTIAL") else "NOT_SUPPORTED"
        cc.supported = any(v == "SUPPORTED" for v in cc.verdicts.values())
        checks.append(cc)
    return checks, {"verify_calls": n_calls}


def judge_completeness(llm, question: str, answer: str) -> float:
    resp = llm.chat([{"role": "user", "content": COMPLETENESS_PROMPT.format(question=question, answer=answer)}],
                    max_tokens=5, temperature=0.0)
    w = resp.text.strip().upper()
    return 1.0 if w.startswith("FULL") else 0.5 if w.startswith("PARTIAL") else 0.0


def not_found_response(question: str, rr: RetrievalResult) -> dict:
    """Structured 'I don't know': what was found, what was not, where to look manually."""
    seen, docs = set(), []
    for h in rr.hits:
        if h.chunk.doc_id not in seen:
            seen.add(h.chunk.doc_id)
            docs.append({"doc_id": h.chunk.doc_id, "title": h.chunk.title, "section": h.chunk.section,
                         "source_url": h.chunk.source_url, "score": round(h.score, 3)})
    return {
        "could_not_answer": question,
        "why": f"retrieval confidence {rr.confidence:.2f} — the closest passages do not appear to contain the answer",
        "closest_passages_found": docs[:5],
        "suggested_documents_to_check_manually": [d["doc_id"] for d in docs[:3]],
    }


def generate_answer(llm, question: str, rr: RetrievalResult, threshold: float, verify: bool = True) -> Answer:
    timings: dict[str, float] = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "llm_calls": 0}
    hits_by_n = {h.rank: h for h in rr.hits}

    def _acc(resp):
        usage["llm_calls"] += 1
        usage["prompt_tokens"] += resp.prompt_tokens or 0
        usage["completion_tokens"] += resp.completion_tokens or 0

    # --- abstain early when retrieval itself looks weak (Phase 3.4) --------------------
    if rr.confidence < threshold or not rr.hits:
        return Answer(
            question=question, status="insufficient",
            answer="I could not find enough information in the indexed documentation to answer this reliably.",
            citations=[], claims=[], flags=["low_retrieval_confidence"],
            confidence={"retrieval": round(rr.confidence, 3), "citation_coverage": 0.0, "completeness": 0.0, "composite": round(0.4 * rr.confidence, 3)},
            retrieval=rr.to_dict(), model=getattr(llm, "model", "?"), timings_ms={**rr.timings_ms}, usage=usage,
            not_found=not_found_response(question, rr),
        )

    # --- grounded generation -------------------------------------------------------------
    resp = llm.chat(build_messages(question, rr.hits))
    _acc(resp)
    timings["generate"] = resp.latency_ms
    status, answer_text = parse_generation(resp.text)

    claims_raw = split_claims(answer_text)
    cited_ns = sorted({n for _, cs in claims_raw for n in cs})
    citations = [
        Citation(n, h.chunk.chunk_id, h.chunk.doc_id, h.chunk.title, h.chunk.section, h.chunk.page, h.chunk.source_url,
                 h.chunk.text[:300])
        for n in cited_ns if (h := hits_by_n.get(n))
    ]
    flags: list[str] = []
    invalid = [n for n in cited_ns if n not in hits_by_n]
    if invalid:
        flags.append(f"invalid_citation_numbers:{invalid}")

    if status == "insufficient":
        return Answer(question=question, status=status, answer=answer_text, citations=citations, claims=[],
                      flags=flags + ["model_reported_insufficient"],
                      confidence={"retrieval": round(rr.confidence, 3), "citation_coverage": 0.0, "completeness": 0.0,
                                  "composite": round(0.4 * rr.confidence, 3)},
                      retrieval=rr.to_dict(), model=resp.model, timings_ms={**rr.timings_ms, **timings}, usage=usage,
                      not_found=not_found_response(question, rr))

    # --- citation verification (Phase 3.2) -------------------------------------------------
    checks: list[ClaimCheck] = []
    if verify and claims_raw:
        import time as _t
        t0 = _t.perf_counter()
        checks, vstats = verify_claims(llm, claims_raw, hits_by_n)
        usage["llm_calls"] += vstats["verify_calls"]
        timings["verify"] = round((_t.perf_counter() - t0) * 1000, 1)
        for cc in checks:
            if not cc.citations:
                flags.append(f"uncited_claim: {cc.claim[:80]}")
            for n, v in cc.verdicts.items():
                if v in ("NOT_SUPPORTED", "INVALID"):
                    flags.append(f"unsupported_citation [{n}]: {cc.claim[:80]}")
    else:
        checks = [ClaimCheck(claim=c, citations=cs, supported=bool(cs)) for c, cs in claims_raw]

    n_claims = len(checks)
    coverage = (sum(1 for c in checks if c.supported) / n_claims) if n_claims else 0.0

    # --- completeness (Phase 3.3) ------------------------------------------------------------
    completeness = 0.0
    if verify:
        import time as _t
        t0 = _t.perf_counter()
        completeness = judge_completeness(llm, question, answer_text)
        usage["llm_calls"] += 1
        timings["completeness"] = round((_t.perf_counter() - t0) * 1000, 1)

    composite = 0.4 * rr.confidence + 0.4 * coverage + 0.2 * completeness
    return Answer(
        question=question, status=status, answer=answer_text, citations=citations, claims=checks,
        confidence={"retrieval": round(rr.confidence, 3), "citation_coverage": round(coverage, 3),
                    "completeness": completeness, "composite": round(composite, 3)},
        flags=flags, retrieval=rr.to_dict(), model=resp.model, timings_ms={**rr.timings_ms, **timings}, usage=usage,
    )
