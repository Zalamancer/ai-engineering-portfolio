"""FastAPI service (guide Phase 5.1): POST /v1/ask, GET /v1/documents, POST /v1/ingest, plus
GET /v1/retrieve for retrieval-only debugging and GET /health. OpenAPI docs at /docs."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import __version__
from .chunking import STRATEGIES
from .config import settings
from .pipeline import get_pipeline

app = FastAPI(title="Hybrid RAG over web-platform docs", version=__version__,
              description="Hybrid (BM25 + dense) retrieval with RRF fusion, cross-encoder reranking, grounded "
                          "generation, citation verification and explicit abstention.")
_ingest_lock = threading.Lock()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    strategy: Literal["fixed", "recursive", "semantic"] | None = Field(None, description="chunking index to query")
    mode: Literal["hybrid", "dense", "sparse"] = "hybrid"
    rerank: bool = True
    verify: bool | None = Field(None, description="run citation verification (default from settings)")
    top_k: int | None = Field(None, ge=1, le=20)


class UploadedDocInfo(BaseModel):
    filename: str
    stored_at: str


@app.get("/health")
def health():
    p = get_pipeline()
    return {"status": "ok", "llm_available": p.llm.is_available(), "llm_model": p.s.llm_model,
            "embedding_model": p.s.embedding_model, "strategies": p.strategies()}


@app.post("/v1/ask")
def ask(req: AskRequest):
    p = get_pipeline()
    if req.strategy and req.strategy not in p.strategies():
        raise HTTPException(404, f"no index for strategy {req.strategy!r}; available: {p.strategies()}")
    if not p.llm.is_available():
        raise HTTPException(503, "LLM endpoint unavailable — start scripts/serve_llm.sh or set RAG_LLM_BASE_URL")
    return p.ask(req.question, req.strategy, req.mode, req.rerank, req.verify, req.top_k).to_dict()


@app.get("/v1/retrieve")
def retrieve(q: str, strategy: str | None = None, mode: str = "hybrid", rerank: bool = True, top_k: int = 5):
    p = get_pipeline()
    if strategy and strategy not in p.strategies():
        raise HTTPException(404, f"no index for strategy {strategy!r}")
    return p.retrieve(q, strategy, mode, rerank, top_k).to_dict()


@app.get("/v1/documents")
def documents(strategy: str | None = None):
    p = get_pipeline()
    docs = p.documents(strategy)
    b = p.bundle(strategy)
    return {"strategy": b.strategy, "count": len(docs), "index": b.manifest, "sync": b.check_sync(), "documents": docs}


@app.post("/v1/ingest")
async def ingest(files: list[UploadFile] = File(...), strategy: Literal["fixed", "recursive", "semantic"] | None = None):
    """Accepts new .md/.txt/.html/.pdf files, stores them under data/raw/uploads/ and rebuilds
    the chosen strategy's indexes (synchronously — the corpus is small)."""
    from .embeddings import get_embedder
    from .index import build_index
    from .loaders import SourceSpec, default_sources, load_sources, write_processed

    up = settings.raw_dir / "uploads"
    up.mkdir(parents=True, exist_ok=True)
    stored: list[UploadedDocInfo] = []
    for f in files:
        if Path(f.filename).suffix.lower() not in {".md", ".txt", ".html", ".htm", ".pdf"}:
            raise HTTPException(415, f"unsupported file type: {f.filename}")
        dest = up / Path(f.filename).name
        with dest.open("wb") as fh:
            shutil.copyfileobj(f.file, fh)
        stored.append(UploadedDocInfo(filename=f.filename, stored_at=str(dest)))
    if not _ingest_lock.acquire(blocking=False):
        raise HTTPException(409, "an ingest is already running")
    try:
        p = get_pipeline()
        strat = strategy or p.s.default_strategy
        specs = default_sources(settings.raw_dir) + [SourceSpec("uploads", up, "*.*", "uploaded by user", "upload://", "n/a")]
        n_docs = write_processed(load_sources(specs), settings.processed_dir / "docs.jsonl")
        from .loaders import read_processed
        manifest = build_index(read_processed(settings.processed_dir / "docs.jsonl"), strat,
                               get_embedder(p.s.embedding_model), p.s, log=lambda *_: None)
        p._bundles.pop(strat, None)
        return {"stored": [s.model_dump() for s in stored], "documents_indexed": n_docs, "index": manifest.__dict__}
    finally:
        _ingest_lock.release()
