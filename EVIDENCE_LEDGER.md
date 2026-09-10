# Evidence ledger

Every measured number in the portfolio traces back to a row here. IDs are stable; artifacts
live under the project folders. "AI-drafted" and "LLM judge" labels are part of the record.

## Project 1 — `01-hybrid-rag/`

| ID | Date | What | Dataset / index version | Command | Result artifact | Headline result |
|---|---|---|---|---|---|---|
| R1-CORPUS | 2026-09-09 | Corpus fetched at pinned commits | see `data/raw/MANIFEST.md` | `scripts/fetch_corpus.sh` | `data/processed/docs.jsonl` (198 docs, 2,117,910 chars) | 4 formats loaded |
| R1-INDEX | 2026-09-09 | Indexes built, 3 strategies | bge-small-en-v1.5; dedup 0.95 | `uv run python scripts/ingest.py --reload` | `data/index/*/manifest.json`, `dedup_log.json` | fixed 3183 chunks (16 dups), recursive 3799 (108), semantic 2404 (23); build 39 / 37 / 88 s |
| R1-TESTS | 2026-09-09 | Unit + integration tests | — | `uv run pytest -q` | terminal | 20 passed |
| R1-QSET | 2026-09-09 | Question set drafted (AI) and quote-checked | `questions.json` 0.1.0-ai-draft | `uv run python scripts/check_questions.py` | `eval/questions.json` | 75 questions (51 lookup / 8 multi-hop / 8 no-answer / 8 ambiguous; 44 dev / 31 held-out); 0 human-verified |
| R1-RETR | 2026-09-09 | Retrieval-only eval, 18 configs × 66 evidence questions | index R1-INDEX | `uv run python scripts/run_eval.py retrieval` | `eval/results/retrieval_eval.json` | baseline (fixed/dense/no-rerank) hit@5 58 %; recursive/hybrid/rerank 82 %; recursive/BM25-only 85 % (BM25 alone ≥ hybrid on this AI-drafted set) |
| R1-SWEEP | 2026-09-09 | RRF weight + abstention threshold sweep, **dev split only** | index R1-INDEX | `uv run python scripts/run_eval.py sweep --strategy recursive` | `eval/results/threshold_sweep.json` | weights inert with reranker on; without reranker sparse-heavy (0.3/0.7) best; threshold 0.40 keeps 100 % answerable, abstains 75 % of no-answer (dev) |
| R1-ANS | 2026-09-09 | Answer-quality runs, 6 configs × 75 questions, generator+judge Qwen3-4B local | index R1-INDEX, questions 0.1.0-ai-draft | `scripts/run_all_answer_evals.sh` | `eval/results/runs/*/summary.json`, `RESULTS.md`, `FAILURES.md` | ANSWER_RESULTS_PLACEHOLDER |

| R1-API | 2026-09-09 | API + UI smoke test | index R1-INDEX | `uv run uvicorn hybrid_rag.api:app --port 8000` + curl; `streamlit run hybrid_rag/ui.py` | terminal | /health ok (llm online, 3 strategies); /v1/documents 198 docs, indexes in sync (3799/3799/3799); /v1/retrieve found Sec-WebSocket-Accept in RFC 6455; /v1/ask answered the StaticFiles html=True question with a verified citation (coverage 1.0); OpenAPI lists 5 paths; validation errors returned as 422; Streamlit health ok |

## Project 2 — `02-model-regression/`

| ID | Date | What | Dataset / prompt | Command | Result artifact | Headline result |
|---|---|---|---|---|---|---|
| R2-TESTS | 2026-09-09 | Unit + fake-model end-to-end tests | golden 0.1.0-ai-draft (fingerprint 1c4455c06434) | `uv run pytest -q` | terminal | 12 passed (schema validation, policy verdicts + McNemar/Wilson, drift, report, alert payload, critical gate with a fake model) |
| R2-BASE | 2026-09-09 | Baseline run, prompt v1, local Qwen3-4B (also judge) | 80 cases, 0 human-verified | `uv run regress run --prompt prompts/v1.yaml --set-baseline` | `runs/20260909-175034_v1/`, `reports/20260909-175034_v1.html` | pass rate 86.3 %, category accuracy 87.5 %, output valid 100 %, latency p50 6.75 s (server shared with other jobs) |
| R2-V2 | 2026-09-09 | Candidate v2 vs baseline (gate) | same | `uv run regress run --prompt prompts/v2.yaml --gate` | `runs/…_v2/comparison.json` | pass 82.5 % (−3.8 pp) → **WARN** (policy 3 pp); 4 regressions (all billing→general) / 1 improvement; exact McNemar p = 0.375 (noise-consistent); exit 0 |
| R2-REVIEW | 2026-09-09 | Human review of the golden dataset by Ihsan Duru in `scripts/review_ui.py` | golden 0.1.0-ai-draft → **0.2.0-reviewed** (fingerprint d6f4a7d7d3be) | — | `data/golden/golden.json` (verification fields) | 80/80 human_verified; 6 labels changed (c005, c006, c013, c016, c056, c073); category mix now billing 16 / technical 23 / account 22 / general 19 |
| R2-VERIFIED | 2026-09-09 | v1 / v2 / v3-bad re-run on the verified dataset | golden 0.2.0-reviewed | `scripts/demo_runs.sh` | `runs/` | v1 85.0 % pass / 87.5 % acc (baseline); v2 82.5 % → **PASS** (−2.5 pp, p=0.688, 4 billing→general regressions / 2 improvements); v3-bad 23.8 % → **CRITICAL** (−61.3 pp, p<0.001, 50 regressions), gate exit 2. First numbers on human-verified ground truth |
| R2-BAD | 2026-09-09 | Intentionally bad prompt v3-bad vs baseline (gate) | same | `uv run regress run --prompt prompts/v3-bad.yaml --gate` | `runs/…_v3-bad/` | pass 25.0 % (−61.3 pp) → **CRITICAL**, gate exit code 2; 51 regressions / 2 improvements; p < 0.001; Slack payload built, not sent |

## Project 3 — `03-agent-orchestration/`

| ID | Date | What | Config | Command | Result artifact | Headline result |
|---|---|---|---|---|---|---|
| R3-TESTS | 2026-09-09 | Orchestration plumbing tests with a scripted model | default budgets, local test target on :8099 | `uv run pytest -q` | terminal | 9 passed: DAG plan validation; tool permissions/schemas/limits/sandbox; full run with reviewer rejection → correction → approval pause/resume → exactly one external write; low-confidence plan modified by human; budget exhaustion → `paused_budget`; unknown tool → bounded retries → explicit failure; killed worker resumed from checkpoint with the write replayed (target received 1 POST); API; memory consolidation + delete |
| R3-DEMO | 2026-09-09 | Live showcase run with local Qwen3-4B | `scripts/demo.py --auto-approve-local` | see command | `data/agentops.db` (run + trace) | run_8e119cab4a12 completed in 695 s; 14 LLM calls, 6 tool calls, 14,044→3,380 tokens; research accepted; analysis needed 3 attempts + take_over (SQL column guessed wrong; reviewer over-strict — both fixed after); writing skipped the required http_post (0 POSTs received) — reviewer rule added. Run 2 after fixes: runs 2–3 paused on wall-clock budget (explicit `paused_budget`); run_19b927715f69 **completed**: 28 LLM calls, 10 tool calls, 38,996→8,719 tokens, 395 s active; approval pause/resume ×2 across worker processes, budget pause → human resume, exactly 1 POST delivered to the local test target; report contained ungrounded numbers (12/8 vs SQL 135/256) → numeric-grounding reviewer rule added and tested |

Labels: all R1-ANS correctness / faithfulness / citation verdicts are **LLM judgments** by the
local 4B model; the question set is **AI-drafted, not human-verified**. No numbers here are
customer impact.
