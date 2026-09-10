"""Hybrid retrieval: dense (Chroma) + sparse (BM25) → Reciprocal Rank Fusion → cross-encoder rerank."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from .chunking import Chunk
from .config import Settings
from .embeddings import Embedder, Reranker
from .index import IndexBundle, tokenize

MODES = ("hybrid", "dense", "sparse")


@dataclass
class Hit:
    chunk: Chunk
    score: float                      # final ordering score (rerank score if reranked, else fusion/raw)
    dense_rank: int | None = None
    dense_score: float | None = None  # cosine similarity
    sparse_rank: int | None = None
    sparse_score: float | None = None  # BM25
    rrf_score: float | None = None
    rerank_score: float | None = None  # cross-encoder logit
    rank: int = 0

    def to_dict(self) -> dict:
        c = self.chunk
        return {
            "rank": self.rank, "chunk_id": c.chunk_id, "doc_id": c.doc_id, "collection": c.collection,
            "title": c.title, "section": c.section, "page": c.page, "source_url": c.source_url,
            "strategy": c.strategy, "char_count": c.char_count, "score": round(self.score, 4),
            "dense_rank": self.dense_rank, "dense_score": _r(self.dense_score), "sparse_rank": self.sparse_rank,
            "sparse_score": _r(self.sparse_score), "rrf_score": _r(self.rrf_score), "rerank_score": _r(self.rerank_score),
            "text": c.text,
        }


def _r(x):
    return None if x is None else round(float(x), 4)


@dataclass
class RetrievalResult:
    query: str
    mode: str
    strategy: str
    reranked: bool
    hits: list[Hit]
    candidates: int
    confidence: float
    timings_ms: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"query": self.query, "mode": self.mode, "strategy": self.strategy, "reranked": self.reranked,
                "candidates": self.candidates, "confidence": round(self.confidence, 4), "timings_ms": self.timings_ms,
                "hits": [h.to_dict() for h in self.hits]}


def reciprocal_rank_fusion(ranked_lists: dict[str, list[str]], weights: dict[str, float], k: int = 60) -> dict[str, float]:
    """RRF: score(d) = Σ_lists w_list / (k + rank_in_list). Weights make dense/sparse tunable."""
    scores: dict[str, float] = {}
    for name, ids in ranked_lists.items():
        w = weights.get(name, 1.0)
        for rank, cid in enumerate(ids, start=1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank)
    return scores


class Retriever:
    def __init__(self, bundle: IndexBundle, embedder: Embedder, reranker: Reranker | None, settings: Settings):
        self.bundle = bundle
        self.embedder = embedder
        self.reranker = reranker
        self.s = settings

    # ---- single-signal retrievers ---------------------------------------------------
    def dense(self, query: str, k: int) -> list[tuple[str, float]]:
        q = self.embedder.embed_queries([query])[0].tolist()
        res = self.bundle.collection.query(query_embeddings=[q], n_results=min(k, len(self.bundle.chunks)), include=["distances"])
        ids, dists = res["ids"][0], res["distances"][0]
        return [(cid, 1.0 - float(d)) for cid, d in zip(ids, dists)]  # cosine distance → similarity

    def sparse(self, query: str, k: int) -> list[tuple[str, float]]:
        scores = self.bundle.bm25.get_scores(tokenize(query))
        if not len(scores):
            return []
        top = np.argsort(-scores)[:k]
        return [(self.bundle.chunks[i].chunk_id, float(scores[i])) for i in top if scores[i] > 0]

    # ---- full pipeline ----------------------------------------------------------------
    def retrieve(self, query: str, mode: str = "hybrid", rerank: bool = True, top_k: int | None = None,
                 candidate_k: int | None = None, dense_weight: float | None = None,
                 sparse_weight: float | None = None) -> RetrievalResult:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        s = self.s
        top_k = top_k or s.final_top_k
        candidate_k = candidate_k or s.rerank_candidates
        t: dict[str, float] = {}
        hits: dict[str, Hit] = {}

        t0 = time.perf_counter()
        if mode in ("hybrid", "dense"):
            k = s.dense_top_k if mode == "hybrid" else candidate_k
            for rank, (cid, sim) in enumerate(self.dense(query, k), start=1):
                hits[cid] = Hit(self.bundle.by_id[cid], sim, dense_rank=rank, dense_score=sim)
            t["dense"] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        if mode in ("hybrid", "sparse"):
            k = s.sparse_top_k if mode == "hybrid" else candidate_k
            for rank, (cid, sc) in enumerate(self.sparse(query, k), start=1):
                h = hits.get(cid) or Hit(self.bundle.by_id[cid], sc)
                h.sparse_rank, h.sparse_score = rank, sc
                hits[cid] = h
            t["sparse"] = (time.perf_counter() - t0) * 1000

        if mode == "hybrid":
            dense_ids = [h.chunk.chunk_id for h in sorted((h for h in hits.values() if h.dense_rank), key=lambda h: h.dense_rank)]
            sparse_ids = [h.chunk.chunk_id for h in sorted((h for h in hits.values() if h.sparse_rank), key=lambda h: h.sparse_rank)]
            fused = reciprocal_rank_fusion(
                {"dense": dense_ids, "sparse": sparse_ids},
                {"dense": s.rrf_dense_weight if dense_weight is None else dense_weight,
                 "sparse": s.rrf_sparse_weight if sparse_weight is None else sparse_weight},
                k=s.rrf_k,
            )
            for cid, sc in fused.items():
                hits[cid].rrf_score = sc
                hits[cid].score = sc
        ordered = sorted(hits.values(), key=lambda h: -h.score)[:candidate_k]
        n_candidates = len(ordered)

        reranked = False
        if rerank and self.reranker is not None and ordered:
            t0 = time.perf_counter()
            scores = self.reranker.score(query, [h.chunk.text for h in ordered])
            for h, sc in zip(ordered, scores):
                h.rerank_score = float(sc)
                h.score = float(sc)
            ordered.sort(key=lambda h: -h.score)
            reranked = True
            t["rerank"] = (time.perf_counter() - t0) * 1000
        final = ordered[:top_k]
        for i, h in enumerate(final, start=1):
            h.rank = i
        return RetrievalResult(query, mode, self.bundle.strategy, reranked, final, n_candidates,
                               retrieval_confidence(final, reranked), {k: round(v, 1) for k, v in t.items()})


def retrieval_confidence(hits: list[Hit], reranked: bool) -> float:
    """0..1 estimate of how relevant the top chunks are (guide Phase 3.3 'retrieval confidence').

    With a cross-encoder: mean sigmoid of the top-3 rerank logits (ms-marco logits are
    roughly calibrated so that >0 means 'relevant'). Without one: best cosine similarity
    rescaled from the empirical [0.45, 0.85] range of bge-small on this corpus.
    Threshold tuning is done on the dev split only (see eval/results/threshold_sweep.json).
    """
    if not hits:
        return 0.0
    if reranked:
        top = [h.rerank_score for h in hits[:3] if h.rerank_score is not None]
        return float(np.mean([1 / (1 + math.exp(-x)) for x in top])) if top else 0.0
    sims = [h.dense_score for h in hits if h.dense_score is not None]
    if not sims:
        return 0.5  # sparse-only: BM25 scores are not comparable across queries
    return float(min(1.0, max(0.0, (max(sims) - 0.45) / 0.40)))
