# Requirements checklist — guide project #15 (pp. 56–59)

| # | Guide requirement | Status | Where / evidence | Adaptation / limitation |
|---|---|---|---|---|
| 1.1 | Supervisor / specialists (research, analysis, writing, code) / reviewer as LangGraph nodes with I/O schemas | ✅ | `agentops/graph.py`, `agents.py` (Pydantic `Plan`, `ReviewVerdict`) | code execution is a tool of the analysis specialist rather than a 4th specialist |
| 1.2 | Task decomposition with dependencies, structured output: description, specialist, inputs, expected output, complexity | ✅ | `Plan`/`PlanTask`, DAG validator; test `test_plan_contract_rejects_bad_dags` | — |
| 1.3 | Tool registry: name, description, in/out schemas, allowed specialists, rate limits; web search, file r/w, sandboxed code, DB query, API calls; every invocation logged | ✅ | `agentops/tools.py`; test `test_tool_registry_…` | http_post allow-listed to the local test target |
| 1.4 | Graph: intake → planning → parallel/sequential execution → review → synthesis → delivery; retry on failure, reroute on reviewer rejection, human escalation on low confidence | ✅ | `graph.py` conditional edges; tests happy path / unavailable tool / low confidence | — |
| 2.1 | Short-term working memory shared during a run (plan, outputs, errors), scoped to the run | ✅ | LangGraph state + `tasks`/`events` tables (SQLite instead of Redis) | adaptation |
| 2.2 | Long-term semantic memory after completion (request, approach, tools, facts) in ChromaDB | ✅ | `memory.py`: episode + facts stored in `synthesize` | — |
| 2.3 | Memory retrieval injected into planning | ✅ | `intake` → `memories` → supervisor prompt block; event `memory_retrieval` | — |
| 2.4 | Importance scoring, consolidation, expiration/decay, memory dashboard, delete endpoint | ✅ | `Memory.touch/consolidate/decay`, UI Memory tab, `DELETE /memory` | consolidation = similarity merge |
| 3.1 | Escalation triggers: low plan confidence, specialist failed twice, sensitive ops, low reviewer score, user request | ✅ | `plan_confidence_threshold`, `max_retries_per_task`, `sensitive_tools`, reviewer `take_over`, `require_plan_approval` | — |
| 3.2 | Approval queue: pause, package context, wait for approve/reject/modify | ✅ | `approvals` table + `interrupt()`; `POST /approvals/{id}`; tests | — |
| 3.3 | Granular levels: notify / approve action / approve plan / take over | ✅ | levels implemented and mapped to triggers | — |
| 3.4 | Review interface: context, progress, decision point, proposed action + reasoning, memories, buttons, chat panel | 🟡 | `agentops/ui.py` Approvals tab (all but chat panel) | chat-with-agent panel not built |
| 4.1 | Full execution tracing (planning, tool calls, reviews, memory, escalations) | ✅ | `events` table, `GET /runs/{id}/trace` | OpenTelemetry not used (structured table instead) |
| 4.2 | Trace explorer UI, colour-coded, expandable prompts/responses | ✅ | UI "Execution trace" per task with status colours | tree = grouped by task |
| 4.3 | Cost/performance tracking per task and aggregated | 🟡 | per-event tokens/latency/cost, per-run totals, ledger | cross-run aggregation only via SQL, no chart |
| 4.4 | Replay system | ❌ | — | stretch; traces hold full prompts/responses |
| 5.1 | Demo scenario: research + extraction + analysis + summary; decomposition, parallel specialists, reviewer catch, memory, human approval | ✅/live pending | `scripts/demo.py`; live result in README when the run finishes | — |
| 5.2 | docker-compose with API, queue, DB, Chroma, workers, UIs + demo script | 🟡 | `docker-compose.yml` (api, worker, console, testtarget) | not built (disk); SQLite instead of Redis/Postgres |
| 5.3 | End-to-end tests: valid plans, tools, reviewer catches bad output, memory helps planning, escalation timing, graceful recovery | ✅ (memory→planning only as retrieval) | `tests/test_agentops.py` (9) | no test that memory *improves* a plan (would need a real model) |
| + | Prompt: budgets (steps, retries, concurrency, time, model usage) enforced in code | ✅ | `config.py`, `llm.py`, `graph.py`; test | — |
| + | Prompt: killed worker resumes without repeating side effects | ✅ | `test_killed_worker_resumes_without_repeating_side_effects` | — |
| + | Prompt: usage ledger reserve/reconcile, disable calls when allowance exhausted | ✅ | `LLM.chat`, `ledger` table, `/ledger` | — |
| + | AWS deployment | ✅ | Lightsail + Bedrock Nova Lite + CloudWatch + S3 + Budget; cloud run completed for $0.0031 | single instance, SSH-tunnel access only |
