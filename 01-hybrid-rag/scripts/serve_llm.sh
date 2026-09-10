#!/usr/bin/env bash
# Starts the local OpenAI-compatible LLM server (mlx_lm, Apple-silicon only).
# Model: Qwen3-4B-Instruct-2507 4-bit (Apache-2.0), ~2.3 GB, downloaded to the Hugging Face cache on first run.
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL="${RAG_LLM_MODEL:-mlx-community/Qwen3-4B-Instruct-2507-4bit}"
PORT="${RAG_LLM_PORT:-8081}"
exec uv run python -m mlx_lm server --model "$MODEL" --port "$PORT" --host 127.0.0.1 "$@"
