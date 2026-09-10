"""Local embedding + cross-encoder reranker wrappers (sentence-transformers).

Adaptation from the guide: the guide specifies OpenAI ``text-embedding-3-small``.
No paid API is authorised for this project, so we use ``BAAI/bge-small-en-v1.5``
(MIT licence, 384-dim, runs on the Mac). The interface is provider-agnostic so
an API embedder can be dropped in later without touching the indexes' callers
(indexes would need rebuilding — the model name is recorded in each index manifest).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, model_name: str, batch_size: int = 64):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_embedding_dimension())
        self._query_prefix = BGE_QUERY_PREFIX if "bge" in model_name.lower() else ""

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.asarray(self.model.encode(list(texts), batch_size=self.batch_size, normalize_embeddings=True,
                                            show_progress_bar=False), dtype=np.float32)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self.embed_documents([self._query_prefix + t for t in texts])


class Reranker:
    """Cross-encoder relevance scorer (guide Phase 2.4)."""

    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self.model = CrossEncoder(model_name)

    def score(self, query: str, passages: Sequence[str]) -> np.ndarray:
        if not passages:
            return np.zeros((0,), dtype=np.float32)
        return np.asarray(self.model.predict([(query, p) for p in passages], show_progress_bar=False), dtype=np.float32)


@lru_cache(maxsize=2)
def get_embedder(model_name: str, batch_size: int = 64) -> Embedder:
    return Embedder(model_name, batch_size)


@lru_cache(maxsize=2)
def get_reranker(model_name: str) -> Reranker:
    return Reranker(model_name)
