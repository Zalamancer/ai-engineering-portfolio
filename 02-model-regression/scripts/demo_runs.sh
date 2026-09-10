#!/usr/bin/env bash
# Demo sequence (guide Phase 6): baseline → candidate → intentionally bad prompt failing the gate.
set -uo pipefail
cd "$(dirname "$0")/.."
echo "=== v1 baseline"; uv run regress run --prompt prompts/v1.yaml --set-baseline
echo "=== v2 candidate (gate)"; uv run regress run --prompt prompts/v2.yaml --gate; echo "exit=$?"
echo "=== v3-bad candidate (gate) — expected to FAIL"; uv run regress run --prompt prompts/v3-bad.yaml --gate; echo "exit=$?"
uv run regress history
