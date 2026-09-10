#!/usr/bin/env bash
# Runs the end-to-end answer-quality evaluation for the configurations compared in RESULTS.md.
# Needs the local LLM server (scripts/serve_llm.sh). Takes ~2-3 h on an M4 with the 4B model.
set -uo pipefail
cd "$(dirname "$0")/.."
run() { echo "=== $*"; uv run python scripts/run_eval.py answers "$@" 2>&1 | grep -v -E "Warning|warn|Batches|Loading weights"; }
run --strategy fixed     --mode dense  --no-rerank      # plain baseline (quickstart-style RAG)
run --strategy recursive --mode hybrid --rerank         # full system, default strategy
run --strategy recursive --mode dense  --rerank         # isolates hybrid vs dense-only
run --strategy recursive --mode sparse --no-rerank      # BM25 alone (best retrieval-only config)
run --strategy fixed     --mode hybrid --rerank         # chunking comparison
run --strategy semantic  --mode hybrid --rerank         # chunking comparison
uv run python scripts/compare.py
