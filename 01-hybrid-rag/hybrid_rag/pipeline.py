"""End-to-end entry point used by the API, the UI, the evaluation scripts and the tests."""
from __future__ import annotations

from functools import lru_cache

from .config import Settings, settings as default_settings
from .embeddings import get_embedder, get_reranker
from .generation import Answer, generate_answer
from .index import IndexBundle, available_strategies, load_index
from .llm import LLMClient
from .retrieval import RetrievalResult, Retriever


class RAGPipeline:
    def __init__(self, settings: Settings | None = None, llm=None, use_reranker: bool = True):
        self.s = settings or default_settings
        self.embedder = get_embedder(self.s.embedding_model, self.s.embedding_batch_size)
        self.reranker = get_reranker(self.s.reranker_model) if use_reranker else None
        self.llm = llm or LLMClient(self.s)
        self._bundles: dict[str, IndexBundle] = {}

    # ---- indexes ---------------------------------------------------------------------
    def strategies(self) -> list[str]:
        return available_strategies(self.s)

    def bundle(self, strategy: str | None = None) -> IndexBundle:
        strategy = strategy or self.s.default_strategy
        if strategy not in self._bundles:
            self._bundles[strategy] = load_index(strategy, self.s)
        return self._bundles[strategy]

    def retriever(self, strategy: str | None = None) -> Retriever:
        return Retriever(self.bundle(strategy), self.embedder, self.reranker, self.s)

    # ---- queries ----------------------------------------------------------------------
    def retrieve(self, question: str, strategy: str | None = None, mode: str = "hybrid", rerank: bool = True,
                 top_k: int | None = None, **kw) -> RetrievalResult:
        return self.retriever(strategy).retrieve(question, mode=mode, rerank=rerank, top_k=top_k, **kw)

    def ask(self, question: str, strategy: str | None = None, mode: str = "hybrid", rerank: bool = True,
            verify: bool | None = None, top_k: int | None = None, threshold: float | None = None) -> Answer:
        rr = self.retrieve(question, strategy, mode, rerank, top_k)
        return generate_answer(self.llm, question, rr,
                               self.s.retrieval_confidence_threshold if threshold is None else threshold,
                               verify=self.s.verify_citations if verify is None else verify)

    def documents(self, strategy: str | None = None) -> list[dict]:
        b = self.bundle(strategy)
        by_doc: dict[str, dict] = {}
        for c in b.chunks:
            d = by_doc.setdefault(c.doc_id, {"doc_id": c.doc_id, "collection": c.collection, "title": c.title,
                                             "source_url": c.source_url, "chunks": 0, "chars": 0})
            d["chunks"] += 1
            d["chars"] += c.char_count
        return sorted(by_doc.values(), key=lambda d: d["doc_id"])


@lru_cache(maxsize=1)
def get_pipeline() -> RAGPipeline:
    return RAGPipeline()
