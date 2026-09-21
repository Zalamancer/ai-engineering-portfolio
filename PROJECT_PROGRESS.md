# Project progress

Last updated: 2026-09-09 (session 1, night). Repo: https://github.com/Zalamancer/ai-engineering-portfolio Plain-language status first, details below.

## Where things stand

| Project | Status | Human action needed? |
|---|---|---|
| 01 Hybrid RAG (#6) | **Built, measured, running locally.** 20 tests pass; retrieval eval (18 configs) and six answer-quality runs done; results + failure analysis in README. | No (question set verified 2026-09-10) |
| 02 Model regression (#1) | **Done locally + on GitHub.** 12 tests; dataset human-verified by Ihsan (80/80); v1 85 %, v2 pass, v3-bad blocked (critical, exit 2); public repo + PR gate workflow running (eval step skipped without model secrets). Slack delivery pending a webhook. | Slack webhook (optional); model secrets for Actions (optional) |
| 03 Agent orchestration (#15) | **Built and live-tested locally.** 11 tests; one full live run completed with approval pause/resume, budget pause/resume and exactly one webhook delivery; five defects found by live runs and fixed. **Deployed to AWS** (Lightsail $12/month, SSH-only, Bedrock Nova Lite, CloudWatch, S3 backup, $20 budget alert); one cloud run completed end to end for $0.003. | Enable MFA on the root user (recommended) |

All three share one local LLM server (Qwen3-4B on the Mac). Running the three evaluation jobs at
once slowed each of them; results are still correct, only wall-clock latency numbers are inflated
and are labelled as such.

## 01 — Hybrid RAG

Implemented: multi-format loader (MD/TXT/HTML/PDF) with section + page metadata over 198 public
docs; three chunkers; Chroma + BM25 indexes from the same chunks with dedup and a sync check;
hybrid retrieval (weighted RRF) + cross-encoder rerank + retrieval confidence; grounded generation
with `[n]` citations, statuses answered / insufficient / ambiguous, claim-level citation
verification, composite confidence, structured not-found response; FastAPI + Streamlit; retrieval
eval over 18 configurations vs the plain baseline; dev-only sweeps; answer-quality runs with LLM
judges; report generator; human review screen.

Checked: 20 tests; all evidence quotes verified in corpus; API/UI smoke test (EVIDENCE_LEDGER R1-API);
retrieval eval (R1-RETR). Honest headline so far: BM25 alone ≥ hybrid+rerank on this AI-drafted set
(85 % vs 82 % hit@5); both far above dense-only baseline (58 %).

Known failures: dedup false positives on templated FastAPI pages; PDF extraction displaces RFC
MUST/SHOULD keywords; 4B model sometimes leaves the first sentence uncited; one eval question took
51 minutes wall-clock because the LLM server was shared with other processes at that moment
(infrastructure artefact, recorded in the run).

## 02 — Model regression detection

Implemented: versioned YAML prompts (v1 baseline, v2 candidate, v3-bad demo); Pydantic output
contract; 80-case golden dataset with edge-case tags (AI-drafted, labelled, review UI); async runner;
scoring (category, JSON validity, summary judge 1–5, latency, tokens); SQLite + JSON storage;
baseline diff with regressed/improved case lists; **policy** thresholds 3 %/8 % plus exact McNemar
p-value and Wilson intervals (explicitly not called significance); 7-run drift check; HTML report with
inline SVG trend; Slack payload builder with outbox (no sending without `--send` + webhook);
Dockerfile; GitHub Actions workflow that skips (and says so) when model secrets are absent.

Checked: 12 tests; baseline v1 measured (EVIDENCE_LEDGER R2-BASE); v2 / v3-bad gate demonstration
on the human-verified dataset (R2-VERIFIED); README results filled.

**2026-09-21 — Jev (TypeSafe System One) backend.** Same golden set, scoring and gate, second
backend selected by `backend: jev` in the prompt YAML: one Choice question per email, typed answer
with per-category probabilities and confidence, no text generation (summary dimension recorded as
not applicable). Baselines are per backend; served model id recorded per run; SQLite migrated
with `confidence` / `probabilities` columns; new commands `confidence-curve`, `versus`, and
`run --model / --golden`. 16 tests. Four gated prompt versions, one change each: 85.0 % → 91.3 %
→ 93.8 % → **97.5 %** category accuracy (0 regressions / 10 improvements vs the jev baseline,
McNemar p = 0.002), vs 87.5 % for the LLM prompt; p50 189 ms vs 4,975 ms; $0.042 per 1k emails.
Held-out (24 AI-drafted cases written after v4 was frozen): 70.8 % → 95.8 %. Confidence gating at
0.80: 88 % auto-handled at 100 % accuracy. Repeat run and `jev-preview` swap: 0 flips. Ledger
R2-JEV-*. Caveats recorded in the README: criteria tuned on the evaluation set, held-out labels
unverified, n = 80, laptop-vs-hosted latency.

## 03 — Agent orchestration

Implemented: LangGraph graph intake → plan → execute → review → synthesize → deliver with SQLite
checkpoints; supervisor structured DAG plans with confidence; three specialists with a bounded tool
loop; tool registry (9 tools, schemas, permissions, rate limits, sandboxed python, read-only SQL,
allow-listed http_post to a local test target, idempotent side effects); reviewer with programmatic
citation check + LLM verdict and bounded corrections; approvals at four levels via LangGraph
interrupt/resume; budgets for steps/LLM calls/tool calls/tokens/time/retries/review rounds/
concurrency/cost + app allowance with a reserve→reconcile ledger; long-term memory in Chroma with
importance/decay/consolidation/delete; leased work queue + worker with crash recovery; FastAPI;
Streamlit console (runs, approvals, trace, memory, ledger); local test target; demo script;
Dockerfile/compose.

Checked: 9 tests (EVIDENCE_LEDGER R3-TESTS). Pending: live demo run result; README results.

## Blockers

- **Disk space** (~1 GB free): no Docker builds, no additional models.
- **Model access**: local 4B only; quality-limited planning/JSON. A paid key is Ihsan's decision.
- Both datasets are now human-verified (2026-09-09/10).

## Next steps

1. Collect the running results → fill README results in all three projects and EVIDENCE_LEDGER placeholders.
2. (done) Both datasets reviewed; RAG answers unchanged so results stand; regression gate re-run on verified labels.
3. (done) Project 3 deployed to AWS; run `scripts/aws_teardown.sh` when the demo is no longer needed to stop the $12/month.
4. Optional: GitHub repo + Actions run for project 2; Slack test channel.
