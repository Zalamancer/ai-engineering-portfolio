"""Load + normalise the raw corpus, then build the dense (Chroma) and sparse (BM25)
indexes for one or more chunking strategies.

    uv run python scripts/ingest.py                 # all three strategies
    uv run python scripts/ingest.py --strategy fixed
    uv run python scripts/ingest.py --reload        # re-parse raw files first
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hybrid_rag.chunking import STRATEGIES  # noqa: E402
from hybrid_rag.config import settings  # noqa: E402
from hybrid_rag.embeddings import get_embedder  # noqa: E402
from hybrid_rag.index import build_index  # noqa: E402
from hybrid_rag.loaders import default_sources, load_sources, read_processed, write_processed  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=STRATEGIES, action="append", help="repeatable; default all")
    ap.add_argument("--reload", action="store_true", help="re-parse data/raw into data/processed/docs.jsonl")
    args = ap.parse_args()

    processed = settings.processed_dir / "docs.jsonl"
    if args.reload or not processed.exists():
        n = write_processed(load_sources(default_sources(settings.raw_dir)), processed)
        print(f"parsed {n} documents -> {processed}")
    docs = read_processed(processed)
    embedder = get_embedder(settings.embedding_model, settings.embedding_batch_size)
    for strategy in args.strategy or STRATEGIES:
        build_index(docs, strategy, embedder, settings)


if __name__ == "__main__":
    main()
