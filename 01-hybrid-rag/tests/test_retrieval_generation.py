import numpy as np
import pytest

from hybrid_rag.chunking import Chunk
from hybrid_rag.generation import parse_generation, split_claims, generate_answer, verify_claims
from hybrid_rag.index import dedup_filter, tokenize
from hybrid_rag.llm import FakeLLM
from hybrid_rag.retrieval import Hit, RetrievalResult, reciprocal_rank_fusion, retrieval_confidence


def test_tokenizer_keeps_compound_identifiers_and_parts():
    toks = tokenize("Set Sec-WebSocket-Key and --proxy-headers via pydantic.BaseSettings")
    assert "sec-websocket-key" in toks and "websocket" in toks
    assert "--proxy-headers" not in toks and "proxy-headers" in toks and "proxy" in toks
    assert "pydantic.basesettings" in toks and "basesettings" in toks


def test_rrf_weights_and_rank_positions():
    scores = reciprocal_rank_fusion({"dense": ["a", "b", "c"], "sparse": ["c", "a"]}, {"dense": 0.7, "sparse": 0.3}, k=60)
    assert scores["a"] == pytest.approx(0.7 / 61 + 0.3 / 62)
    assert scores["c"] == pytest.approx(0.7 / 63 + 0.3 / 61)
    assert scores["b"] == pytest.approx(0.7 / 62)
    assert sorted(scores, key=scores.get, reverse=True)[0] == "a"


def test_dedup_filter_drops_near_duplicates_only():
    v = np.array([[1, 0, 0], [0.999, 0.04, 0], [0, 1, 0]], dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    kept, dropped = dedup_filter(v, 0.95)
    assert kept == [0, 2] and dropped[0][0] == 1 and dropped[0][2] > 0.95


def _chunk(i, text):
    return Chunk(f"c{i}", f"doc{i}", "t", "/p", "http://u", "T", f"Sec {i}", None, "fixed", i, 0, len(text), len(text), text)


def test_retrieval_confidence_from_rerank_scores():
    hits = [Hit(_chunk(1, "x"), 5.0, rerank_score=5.0), Hit(_chunk(2, "y"), -6.0, rerank_score=-6.0)]
    assert retrieval_confidence(hits, reranked=True) == pytest.approx((1 / (1 + np.exp(-5)) + 1 / (1 + np.exp(6))) / 2)
    assert retrieval_confidence([], True) == 0.0


def test_parse_generation_and_claim_split():
    status, body = parse_generation("STATUS: ambiguous\nANSWER:\nTerm X means A in Uvicorn [1]. In FastAPI it means B [2][3].")
    assert status == "ambiguous"
    claims = split_claims(body)
    assert claims == [("Term X means A in Uvicorn.", [1]), ("In FastAPI it means B.", [2, 3])]
    assert parse_generation("just text")[0] == "answered"


def _rr(hits, conf):
    for i, h in enumerate(hits, 1):
        h.rank = i
    return RetrievalResult("q", "hybrid", "fixed", True, hits, len(hits), conf)


def test_generate_answer_abstains_on_low_confidence_without_calling_llm():
    llm = FakeLLM()
    rr = _rr([Hit(_chunk(1, "irrelevant"), -8.0, rerank_score=-8.0)], conf=0.05)
    ans = generate_answer(llm, "q", rr, threshold=0.35)
    assert ans.status == "insufficient" and ans.not_found and llm.calls == []
    assert ans.not_found["closest_passages_found"][0]["doc_id"] == "doc1"


def test_generate_answer_verifies_citations_and_flags_unsupported():
    passage_ok = "The default port is 8000."
    passage_bad = "Cookies are stored by the user agent."
    llm = FakeLLM(rules=[  # checked in order: the completeness prompt also contains "QUESTION:"
        ("Does the ANSWER address", "FULL"),
        ("QUESTION: default port", "STATUS: answered\nANSWER:\nThe default port is 8000 [1]. It also enables TLS [2]. Restart is required."),
        (passage_ok, "SUPPORTED"),
        (passage_bad, "NOT_SUPPORTED"),
    ])
    rr = _rr([Hit(_chunk(1, passage_ok), 4.0, rerank_score=4.0), Hit(_chunk(2, passage_bad), 3.0, rerank_score=3.0)], conf=0.9)
    ans = generate_answer(llm, "default port", rr, threshold=0.35)
    assert ans.status == "answered"
    assert [c.n for c in ans.citations] == [1, 2]
    verdicts = {c.claim: c.verdicts for c in ans.claims}
    assert verdicts["The default port is 8000."] == {1: "SUPPORTED"}
    assert verdicts["It also enables TLS."] == {2: "NOT_SUPPORTED"}
    assert any(f.startswith("unsupported_citation [2]") for f in ans.flags)
    assert any(f.startswith("uncited_claim") for f in ans.flags)
    assert ans.confidence["citation_coverage"] == pytest.approx(1 / 3, abs=1e-3)
    assert ans.confidence["completeness"] == 1.0


def test_invalid_citation_number_is_flagged():
    llm = FakeLLM(rules=[("QUESTION", "STATUS: answered\nANSWER:\nSomething true [7]."), ("Does the ANSWER", "FULL")])
    rr = _rr([Hit(_chunk(1, "p"), 4.0, rerank_score=4.0)], conf=0.9)
    ans = generate_answer(llm, "q", rr, threshold=0.35)
    assert ans.claims[0].verdicts == {7: "INVALID"} and any("invalid_citation_numbers" in f for f in ans.flags)
