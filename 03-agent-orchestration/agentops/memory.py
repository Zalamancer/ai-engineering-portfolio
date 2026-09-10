"""Long-term semantic memory (guide Phase 2.2–2.4): records in SQLite, vectors in ChromaDB.
Importance grows with access, decays over time; near-duplicate memories are consolidated;
a delete endpoint removes a user's memories from both stores."""
from __future__ import annotations

import hashlib
from typing import Callable, Sequence

import numpy as np

from .config import Settings
from .db import DB, now


def hash_embedder(dim: int = 64) -> Callable[[Sequence[str]], np.ndarray]:
    """Deterministic, model-free embedder for tests (bag of hashed tokens)."""
    def embed(texts):
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in t.lower().split():
                out[i, int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
        n = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.clip(n, 1e-9, None)
    return embed


class Memory:
    def __init__(self, settings: Settings, db: DB, embed: Callable[[Sequence[str]], np.ndarray] | None = None, collection: str = "memory"):
        import chromadb
        self.s = settings
        self.db = db
        self.embed = embed or self._st_embedder(settings.embedding_model)
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.col = chromadb.PersistentClient(path=str(settings.chroma_dir)).get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})

    @staticmethod
    def _st_embedder(model_name: str):
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(model_name)
        return lambda texts: np.asarray(m.encode(list(texts), normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)

    # ---- write ------------------------------------------------------------------------------
    def store(self, kind: str, text: str, meta: dict | None = None, run_id: str | None = None, importance: float = 1.0, user_id: str = "default") -> str:
        meta = {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in (meta or {}).items()}
        mid = self.db.add_memory(kind, text, meta, run_id, importance, user_id)
        self.col.add(ids=[mid], embeddings=self.embed([text]).tolist(), documents=[text],
                     metadatas=[{**meta, "kind": kind, "user_id": user_id, "run_id": run_id or ""}])
        return mid

    # ---- read -------------------------------------------------------------------------------
    def search(self, query: str, k: int = 5, user_id: str | None = None) -> list[dict]:
        if self.col.count() == 0:
            return []
        where = {"user_id": user_id} if user_id else None
        res = self.col.query(query_embeddings=self.embed([query]).tolist(), n_results=min(k, self.col.count()),
                             where=where, include=["documents", "metadatas", "distances"])
        ids = res["ids"][0]
        self.db.touch_memory(ids)  # frequently retrieved memories become more important
        return [{"memory_id": i, "text": d, "kind": m.get("kind"), "run_id": m.get("run_id"), "similarity": round(1 - dist, 3)}
                for i, d, m, dist in zip(ids, res["documents"][0], res["metadatas"][0], res["distances"][0])]

    # ---- management ----------------------------------------------------------------------------
    def delete(self, memory_id: str | None = None, user_id: str | None = None) -> int:
        if memory_id:
            self.col.delete(ids=[memory_id])
            return self.db.delete_memory(memory_id=memory_id)
        if user_id:
            got = self.col.get(where={"user_id": user_id}, include=[])
            if got["ids"]:
                self.col.delete(ids=got["ids"])
            return self.db.delete_memory(user_id=user_id)
        return 0

    def decay(self, factor: float = 0.98) -> None:
        self.db.decay_memories(factor)

    def consolidate(self, threshold: float = 0.92) -> list[dict]:
        """Merge near-duplicate memories: keep the more important one, fold the other's text in."""
        got = self.col.get(include=["embeddings", "documents", "metadatas"])
        ids = got["ids"]
        if len(ids) < 2:
            return []
        embs = np.asarray(got["embeddings"], dtype=np.float32)
        embs /= np.clip(np.linalg.norm(embs, axis=1, keepdims=True), 1e-9, None)
        sims = embs @ embs.T
        imp = {m["memory_id"]: m["importance"] for m in self.db.memories(limit=10_000)}
        merged, removed = [], set()
        for i in range(len(ids)):
            if ids[i] in removed:
                continue
            for j in range(i + 1, len(ids)):
                if ids[j] in removed or sims[i, j] < threshold:
                    continue
                keep, drop = (i, j) if imp.get(ids[i], 0) >= imp.get(ids[j], 0) else (j, i)
                new_text = got["documents"][keep] + "\n(also: " + got["documents"][drop][:200] + ")"
                self.col.update(ids=[ids[keep]], documents=[new_text], embeddings=self.embed([new_text]).tolist())
                with self.db.conn() as c:
                    c.execute("UPDATE memory SET text=?, importance=importance+? WHERE memory_id=?", (new_text, imp.get(ids[drop], 0), ids[keep]))
                self.delete(memory_id=ids[drop])
                removed.add(ids[drop])
                merged.append({"kept": ids[keep], "removed": ids[drop], "similarity": round(float(sims[i, j]), 3)})
        return merged

    def dashboard(self, user_id: str | None = None) -> dict:
        rows = self.db.memories(user_id=user_id)
        return {"count": len(rows), "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in {r["kind"] for r in rows}},
                "memories": [{k: r[k] for k in ("memory_id", "kind", "text", "importance", "access_count", "run_id", "user_id")} for r in rows]}
