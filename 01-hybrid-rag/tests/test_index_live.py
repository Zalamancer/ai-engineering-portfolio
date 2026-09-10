"""Tests that need the built indexes (skipped if scripts/ingest.py has not run)."""
import pytest

from hybrid_rag.config import settings
from hybrid_rag.index import available_strategies, load_index


@pytest.mark.skipif(not available_strategies(settings), reason="indexes not built")
@pytest.mark.parametrize("strategy", available_strategies(settings))
def test_indexes_in_sync(strategy):
    b = load_index(strategy, settings)
    s = b.check_sync()
    assert s["in_sync"], s
    assert s["chroma_count"] == s["bm25_count"] == s["chunk_count"] > 1000
    assert all(c.strategy == strategy for c in b.chunks)


@pytest.mark.skipif(not available_strategies(settings), reason="indexes not built")
def test_hybrid_retrieval_finds_exact_identifier():
    from hybrid_rag.pipeline import RAGPipeline
    from hybrid_rag.llm import FakeLLM
    p = RAGPipeline(llm=FakeLLM())
    rr = p.retrieve("What does the --proxy-headers flag do?", strategy=available_strategies(settings)[0], mode="hybrid")
    assert rr.hits and any("proxy-headers" in h.chunk.text for h in rr.hits)
    assert 0.0 <= rr.confidence <= 1.0
    sparse = p.retrieve("Sec-WebSocket-Accept", mode="sparse", rerank=False)
    assert "Sec-WebSocket-Accept" in sparse.hits[0].chunk.text
