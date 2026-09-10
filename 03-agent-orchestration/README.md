# 03 · Agent orchestration with tool use, memory and human-in-the-loop

Guide project #15 (BASWE "15 AI Engineering Projects", pp. 56–59). A **supervisor** agent
decomposes a request into a dependency-ordered plan, **specialists** (research / analysis /
writing) execute the tasks with registered, schema-validated tools, a **reviewer** checks every
output and can send it back for a bounded correction, **humans** approve plans and sensitive
actions (the run pauses and resumes), all state and memory live outside the agent process, every
budget is enforced in code, and every decision is recorded in an inspectable trace.

Built and verified locally first. This is the only project intended for AWS later (see
`../AWS_COST_PLAN.md`); nothing has been provisioned.

## Architecture

```
POST /runs ─► runs table (SQLite, leased) ◄─ worker(s): claim → drive graph → release
                                                    │
        LangGraph (checkpointed to SQLite after every node; thread_id = run_id)
        intake ─► plan ─► [approve_plan?] ─► execute ─► review ─► … ─► synthesize ─► deliver
          │        │                          │  ▲        │
      memory    supervisor              specialists │   reviewer (accept | reject+feedback,
      retrieval structured plan         bounded tool loop  ≤ max_review_rounds, then take_over)
                (confidence, DAG)       [approve_action? for sensitive tools]
                                                    │
                                     ToolRegistry: docs_search · web_search · fetch_url · read_file ·
                                     write_file* · python_exec (sandboxed) · sql_query (read-only) ·
                                     http_post* (allow-listed local test target) · memory_search
                                     (*sensitive → human approval; side effects idempotent per run/task/args)
 Outside the process: runs · tasks · events(trace) · approvals · ledger · memory(+Chroma) · side_effects · checkpoints
```

Human-in-the-loop levels (guide Phase 3.3): **notify** (trace event only), **approve_action**
(sensitive tool call), **approve_plan** (low supervisor confidence or user request),
**take_over** (reviewer still rejects after the allowed rounds; the human supplies the output).

Budgets enforced in code (all configurable, see `.env.example`): max graph steps, LLM calls,
tool calls, total tokens, wall-clock seconds, retries per task, review rounds, tool turns per
task, concurrency, per-run cost and a whole-app allowance. Exhaustion produces the explicit state
`paused_budget` with the reason; unavailable tools and repeated failures produce `failed` tasks
with retries logged and a final result that lists what is missing.

## Setup and run

```bash
cd 03-agent-orchestration
uv sync
../01-hybrid-rag/scripts/serve_llm.sh            # local LLM on :8081 (or set AO_LLM_BASE_URL to another endpoint)
uv run python scripts/seed_demo_db.py            # read-only analytics DB for the analysis specialist
uv run pytest -q                                 # 9 tests, scripted model, ~15 s
uv run uvicorn agentops.api:app --port 8010      # API (+ /docs)
uv run uvicorn agentops.testtarget:app --port 8099   # local "team webhook" for external writes
uv run python -m agentops.worker                 # one or more workers
uv run streamlit run agentops/ui.py              # operator console: progress, approvals, traces, memory, ledger
# or the whole showcase in one process:
uv run python scripts/demo.py                    # pauses at approvals; decide in the console or POST /approvals/{id}
uv run python scripts/demo.py --auto-approve-local   # approves only writes to the LOCAL test target, labelled as script-approved
```

Docker: `Dockerfile` + `docker-compose.yml` (api, worker, console, testtarget) — written, **not built on this
Mac** (disk). The compose replaces the guide's Redis/Celery/Postgres/Chroma containers with a
shared SQLite volume + embedded Chroma; roles are identical and the storage layer is one file.

## What the tests prove (scripted model, no quality claims)

| Requirement | Test |
|---|---|
| Supervisor plan is a validated DAG with specialists, dependencies, inputs, expected output, complexity | `test_plan_contract_rejects_bad_dags` |
| Tools: permissions per specialist, schema validation, rate limits, sandbox and allow-lists, every call logged | `test_tool_registry_validates_permissions_args_and_limits` |
| Full run: memory retrieval → plan → research with citations → reviewer rejects once → bounded correction → sensitive write pauses → human approves → exactly one external write → synthesis → memory stored | `test_happy_path_with_bounded_review_correction_and_sensitive_approval` |
| Low-confidence plan pauses; human modifies the plan; run resumes with the new plan | `test_low_confidence_plan_pauses_and_human_can_modify` |
| Budget exhaustion → explicit `paused_budget` with reason and trace event | `test_budget_exhaustion_produces_explicit_paused_state` |
| Unknown tool → bounded retries → explicit task failure surfaced in the result caveats | `test_unavailable_tool_leads_to_explicit_failure_after_bounded_retries` |
| Worker killed right after an external write → new worker resumes from checkpoint, the write is replayed from the idempotency table, target receives it once | `test_killed_worker_resumes_without_repeating_side_effects` |
| API: submit, inspect, trace totals, approvals resolve once, ledger | `test_api_surfaces_runs_approvals_trace_and_ledger` |
| Memory: consolidation of near-duplicates, per-user delete from both stores | `test_memory_consolidation_and_delete` |

## Live run with the local model

See the Results section below (filled from `scripts/demo.py` output and the stored trace). The
trace contains only real events: model prompts/responses, tool inputs/outputs, latencies, token
counts as reported by the server, reviewer verdicts, approval records. No hidden reasoning is
invented; when the server reports no token usage the field is null.

**Run 1 — `run_8e119cab4a12` (2026-09-09, `scripts/demo.py --auto-approve-local`, LLM server shared with two other jobs).**
Status `completed` in 695 s · 59 trace events · 14 LLM calls · 6 tool calls · 14,044 prompt / 3,380 completion tokens (as reported by the server) · cost $0 (local model).

| Task | Specialist | Outcome | What the trace shows |
|---|---|---|---|
| 1 Research proxy header handling | research | done, reviewer accepted (5/5) | one `docs_search` call; final output cited the Starlette middleware page and FastAPI "Behind a Proxy" — both present in the retrieved evidence |
| 2 Analyse documentation mentions | analysis | done after **3 attempts, 2 reviewer rejections, then `take_over` escalation** (auto-approved by the demo script, labelled) | four `sql_query` calls failed with `no such column: content` (the model guessed a column that does not exist); the specialist fell back to restating the research findings; the reviewer rejected each time for citations not retrieved by *this* task |
| 3 Write and post report | writing | done, reviewer accepted | the model returned the report as final **without calling `http_post`** — the test target received 0 POSTs |

Two defects surfaced by this run and fixed afterwards (tests still 9/9):
1. The reviewer's citation check ignored evidence inherited from dependency tasks, so a correct downstream
   citation was treated as unsupported. Fixed: dependency outputs' citations count as evidence.
2. The SQL tool's description did not include the schema, and errors did not either. Fixed: schema text in the
   tool description and appended to SQL errors.
Also added a programmatic reviewer rule: a writing task whose description requires posting is rejected (with
feedback) when no `http_post` call was made.

**Runs 2–3** hit the wall-clock budget under server contention (`paused_budget`, explicit state) and exposed defects 3–4 below.

**Run 4** — `run_19b927715f69` (2026-09-09, started by `scripts/demo.py`, then driven by plain `agentops.worker --once` processes):
status **completed** · 95 trace events · 28 LLM calls · 10 tool calls · 38,996 prompt / 8,719 completion tokens · 395 s of active
processing spread over ~40 min of wall clock (the LLM server was shared with the RAG evaluation).

| Task | Specialist | Outcome |
|---|---|---|
| 1 Research | research | done first time, reviewer 5/5, two `docs_search` calls, four cited doc URLs all retrieved |
| 2 Count sections (SQL) | analysis | done after 3 attempts / 2 rejections; SQL now worked (135 proxy / 256 HTTPS sections), reviewer 5/5 |
| 3 Write + post report | writing | done after 2 attempts / 1 rejection (first attempt skipped the post → rejected by the new rule); `http_post` paused for approval, was approved (labelled: demo operator, local test target), resumed and **delivered exactly one POST** to the test receiver |

Things this run exercised for real: budget pause (`max_wall_seconds` hit while the server was slow) → human raised the limit
→ `POST /runs/{id}/resume` path → continued from the checkpoint; two approval pauses/resumes across separate worker
processes; recovery of the run by a worker that had not started it; episode + facts written to long-term memory (the
next run's planner retrieved them).

Defects found by this run and fixed afterwards (tests now 11/11):
3. After approving a sensitive action, the specialist was asked again and produced slightly different arguments, so a *new*
   approval was requested (a loop). Fixed: an approved action is executed exactly as approved, without a new model call.
4. Wall-clock budget counted idle time (worker dead, human deciding). Fixed: only active node time counts.
5. **Quality failure the reviewer missed:** the final report states "12 sections mention proxy and 8 mention HTTPS" while the
   SQL result was 135 / 256 — the writer invented numbers and the analysis task's accepted output had dropped them. Fixed
   going forward with a programmatic reviewer rule: any multi-digit number in an analysis/writing output must appear in a tool
   result or an upstream output, otherwise the task is rejected with feedback (covered by a test). The stored run keeps the
   wrong numbers as evidence.

Honest reading: the plumbing behaved as designed (bounded corrections, escalation, trace, budget accounting),
but the 4B local model's task execution quality is low — it guesses schemas and skips required actions. The
supervisor's stated confidence (0.95) was not a reliable predictor of execution quality.


## Cloud deployment (AWS, 2026-09-10)

Deployed to a Lightsail `small_3_0` instance in us-east-1 ($12/month), SSH-only firewall, four systemd services
(API, worker, console, local test target) bound to localhost and reached through an SSH tunnel; model = **Amazon Bedrock
Nova Lite** through the Converse API (IAM user limited to Bedrock + CloudWatch agent); logs shipped to CloudWatch
group `agentops` with 7-day retention; database backed up to a private S3 bucket with 30-day expiry; AWS Budget
$20/month with e-mail alerts. Scripts: `scripts/aws_deploy.sh`, `deploy/server_setup.sh`, `scripts/aws_backup.sh`,
`scripts/aws_teardown.sh`. Idle memory on the server: 565 MB of 1910 MB.

**Cloud run `run_ff918d661db6`** driven entirely through the production path (POST /runs → systemd worker → approval via
POST /approvals → completion):

| | value |
|---|---|
| status | **completed** in **51 s** wall clock |
| model calls / tool calls | 23 / 4 |
| tokens | 24,007 in / 6,790 out (as reported by Bedrock) |
| **cost** (ledger, reserve→reconcile) | **$0.0031** |
| tasks | research done (2 attempts: the first exhausted its tool turns), analysis done (SQL first time), writing done after the reviewer rejected the first draft for not posting |
| approvals | 1 (`http_post` to the local test target, approved through the API) |
| external writes | exactly 1 POST received by the test target |
| citations | 2 doc URLs, both retrieved by the research task |

The cloud model is ~15× faster than the local 4B model (51 s vs ~700 s of active time) and still made the same class
of mistakes the reviewer rules were written for (skipping the required post). One earlier cloud run (`run_83e93a4ecbe7`)
**failed** in 32 s for $0.0025 because Nova copied the raw JSON schema of a tool as its arguments and then repeated the
same search until its turns ran out — fixed by showing example-style arguments and blocking repeated identical calls
(tests 14/14). A caveat on the analysis numbers: the count the model reports is whatever query it chose to run
(6 proxy / 14 HTTPS here, 135 / 256 with a different query locally); the reviewer only checks that the numbers come from a
real tool result, not that the query was the best one.

## Adaptations from the guide (and why)

| Guide | Here | Why |
|---|---|---|
| OpenAI + Anthropic multi-model routing | one local Qwen3-4B endpoint (roles can use different models via `AO_REVIEWER_MODEL`) | no paid API authorised |
| PostgreSQL + Redis + Celery | SQLite (WAL) tables incl. a leased work queue; LangGraph SQLite checkpointer | no Postgres/Redis on this Mac and ~1 GB free disk; same guarantees needed by the tests (durable state, crash recovery, at-most-once side effects) are met and tested. Swapping the DSN is the only change for Postgres |
| MCP tool framework | custom registry with Pydantic schemas | MCP was optional ("Custom + MCP"); registry is the guide's spec |
| OpenTelemetry spans | structured `events` table with the same attributes (agent, kind, latency, tokens, cost, status) | keeps the trace queryable offline; an OTel exporter can read the table |
| Replay system (Phase 4.4) | not built | stretch goal; traces contain full prompts/responses so replay is possible later |
| Web search via a paid API | DuckDuckGo (free) behind `AO_WEB_SEARCH_LIVE`, offline fixture by default; `docs_search` over the project-1 corpus for deterministic, citable research | reproducibility and no keys |

## Limitations

- The 4B local model is weak at multi-step planning and strict JSON; the run loop tolerates
  invalid replies (bounded retries) but live-run quality is limited. Plumbing is proven by tests;
  quality numbers come only from real runs and are labelled.
- `python_exec` is a lightweight sandbox (subprocess, isolated mode, empty env, rlimits, blocked
  imports) — not a VM. Do not run untrusted code with it in production.
- Memory consolidation is embedding-similarity merging, not LLM summarisation.
- AWS: single small instance, no autoscaling/HA; IAM deploy user is broader than least privilege (documented in AWS_COST_PLAN.md).
