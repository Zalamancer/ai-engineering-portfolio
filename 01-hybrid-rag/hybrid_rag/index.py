"""Build and load the two synchronised indexes per chunking strategy:
ChromaDB (dense) and BM25 (sparse), plus near-duplicate filtering (guide Phase 1.3–1.4).
"""
from __future__ import annotations

import json
import pickle
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk, chunk_document
from .config import Settings
from .embeddings import Embedder
from .loaders import LoadedDocument

_TOKEN_RE = re.compile(r"[a-z0-9_]+(?:[-.][a-z0-9_]+)*")


def tokenize(text: str) -> list[str]:
    """Keeps compound technical identifiers (``Sec-WebSocket-Key``, ``--proxy-headers``,
    ``pydantic.BaseSettings``) as single tokens AND emits their parts."""
    text = text.lower()
    toks: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        toks.append(tok)
        if "-" in tok or "." in tok:
            toks.extend(p for p in re.split(r"[-.]", tok) if p)
    return toks


@dataclass
class IndexManifest:
    strategy: str
    embedding_model: str
    n_docs: int
    n_chunks_before_dedup: int
    n_chunks: int
    n_duplicates_skipped: int
    dedup_threshold: float
    built_at: str
    build_seconds: float
    settings: dict


class IndexBundle:
    def __init__(self, strategy: str, chunks: list[Chunk], bm25: BM25Okapi, collection, manifest: dict):
        self.strategy = strategy
        self.chunks = chunks
        self.by_id = {c.chunk_id: c for c in chunks}
        self.bm25 = bm25
        self.collection = collection
        self.manifest = manifest

    def check_sync(self) -> dict:
        """Both indexes must stay in sync: same ids, same count."""
        chroma_ids = set(self.collection.get(include=[])["ids"])
        chunk_ids = set(self.by_id)
        return {
            "chroma_count": len(chroma_ids),
            "bm25_count": len(self.bm25.doc_len) if hasattr(self.bm25, "doc_len") else self.bm25.corpus_size,
            "chunk_count": len(self.chunks),
            "in_sync": chroma_ids == chunk_ids and len(self.chunks) == self.bm25.corpus_size,
        }


def _chroma_client(path: Path):
    import chromadb

    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def dedup_filter(embs: np.ndarray, threshold: float, keep: np.ndarray | None = None) -> tuple[list[int], list[tuple[int, int, float]]]:
    """Greedy near-duplicate filter over normalised embeddings.
    Returns (kept indices, [(dropped_idx, kept_idx_it_duplicates, cosine)])."""
    kept: list[int] = []
    dropped: list[tuple[int, int, float]] = []
    kept_vecs = [] if keep is None else [keep]
    for i in range(len(embs)):
        if kept_vecs:
            mat = np.vstack(kept_vecs) if len(kept_vecs) > 1 else kept_vecs[0]
            sims = mat @ embs[i]
            j = int(np.argmax(sims))
            if sims[j] > threshold:
                dropped.append((i, kept[j] if keep is None else j - (len(keep) if False else 0), float(sims[j])))
                continue
        kept.append(i)
        kept_vecs = [np.vstack([kept_vecs[0], embs[i][None, :]])] if kept_vecs else [embs[i][None, :]]
    return kept, dropped


def build_index(docs: Iterable[LoadedDocument], strategy: str, embedder: Embedder, settings: Settings,
                log=print) -> IndexManifest:
    t0 = time.time()
    docs = list(docs)
    out_dir = settings.strategy_dir(strategy)
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"[{strategy}] chunking {len(docs)} documents ...")
    chunks: list[Chunk] = []
    for d in docs:
        chunks.extend(chunk_document(d, strategy, settings, embed=embedder.embed_documents))
    n_before = len(chunks)
    log(f"[{strategy}] {n_before} chunks; embedding ...")
    embs = embedder.embed_documents([c.text for c in chunks])

    log(f"[{strategy}] near-duplicate check (cosine > {settings.dedup_cosine_threshold}) ...")
    kept_idx, dropped = dedup_filter(embs, settings.dedup_cosine_threshold)
    kept_set = set(kept_idx)
    dedup_log = [
        {"dropped_chunk": chunks[i].chunk_id, "dropped_doc": chunks[i].doc_id, "dropped_section": chunks[i].section,
         "kept_chunk": chunks[kept_idx[k]].chunk_id if k < len(kept_idx) else None,
         "kept_doc": chunks[kept_idx[k]].doc_id if k < len(kept_idx) else None, "cosine": round(sim, 4)}
        for i, k, sim in dropped
    ]
    chunks = [c for i, c in enumerate(chunks) if i in kept_set]
    embs = embs[kept_idx]
    for new_i, c in enumerate(chunks):
        c.chunk_index = new_i  # dense index position == bm25 corpus position

    # --- ChromaDB (dense) -----------------------------------------------------------
    client = _chroma_client(out_dir / "chroma")
    try:
        client.delete_collection("chunks")
    except Exception:
        pass
    col = client.create_collection("chunks", metadata={"hnsw:space": "cosine"})
    B = 512
    for i in range(0, len(chunks), B):
        batch = chunks[i:i + B]
        col.add(ids=[c.chunk_id for c in batch], embeddings=embs[i:i + B].tolist(),
                documents=[c.text for c in batch], metadatas=[c.metadata() for c in batch])

    # --- BM25 (sparse) over exactly the same chunks --------------------------------------
    bm25 = BM25Okapi([tokenize(c.text) for c in chunks])
    with (out_dir / "bm25.pkl").open("wb") as fh:
        pickle.dump(bm25, fh)
    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in chunks:
            fh.write(json.dumps(c.__dict__, ensure_ascii=False) + "\n")
    np.save(out_dir / "embeddings.npy", embs)
    (out_dir / "dedup_log.json").write_text(json.dumps(dedup_log, indent=1))

    manifest = IndexManifest(
        strategy=strategy, embedding_model=embedder.model_name, n_docs=len(docs), n_chunks_before_dedup=n_before,
        n_chunks=len(chunks), n_duplicates_skipped=len(dropped), dedup_threshold=settings.dedup_cosine_threshold,
        built_at=time.strftime("%Y-%m-%dT%H:%M:%S"), build_seconds=round(time.time() - t0, 1),
        settings={k: v for k, v in settings.model_dump().items() if k.startswith(("fixed_", "recursive_", "semantic_"))},
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest.__dict__, indent=1, default=str))
    log(f"[{strategy}] done: {len(chunks)} chunks ({len(dropped)} duplicates skipped) in {manifest.build_seconds}s")
    return manifest


def load_index(strategy: str, settings: Settings) -> IndexBundle:
    d = settings.strategy_dir(strategy)
    if not (d / "manifest.json").exists():
        raise FileNotFoundError(f"no index for strategy {strategy!r} at {d}; run scripts/ingest.py")
    chunks = [Chunk(**json.loads(line)) for line in (d / "chunks.jsonl").open(encoding="utf-8") if line.strip()]
    with (d / "bm25.pkl").open("rb") as fh:
        bm25 = pickle.load(fh)
    col = _chroma_client(d / "chroma").get_collection("chunks")
    return IndexBundle(strategy, chunks, bm25, col, json.loads((d / "manifest.json").read_text()))


def available_strategies(settings: Settings) -> list[str]:
    return sorted(p.name for p in settings.index_dir.glob("*") if (p / "manifest.json").exists())
