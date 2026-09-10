# AI Engineering Portfolio

Three portfolio projects built from the BASWE "15 AI Engineering Projects" guide
(project identities and use cases kept as written; substitutions documented in
`SOURCE_MAPPING.md`).

| Order | Folder | Guide project | Runs where | Status |
|---|---|---|---|---|
| 1 | [`01-hybrid-rag/`](01-hybrid-rag/) | #6 RAG Pipeline with Hybrid Search Over Internal Docs (pp. 20–23) | Local Mac only | Built, tests pass, evals running — see `PROJECT_PROGRESS.md` |
| 2 | [`02-model-regression/`](02-model-regression/) | #1 Model Regression Detection System (pp. 3–5) | Local + GitHub Actions | Built, 12 tests pass, live runs in progress; GitHub not connected |
| 3 | [`03-agent-orchestration/`](03-agent-orchestration/) | #15 Agent Orchestration with Tool Use, Memory, HITL (pp. 56–59) | Local first, then AWS (≤ $30/mo) | Built locally, 9 tests pass, live demo in progress; AWS untouched |

Each project is independently runnable and has its own README with setup,
architecture, results, failure analysis and demo script.

Portfolio-level tracking documents:

- `PROJECT_PROGRESS.md` — what is implemented, checked, failing, blocked; human actions needed.
- `SOURCE_MAPPING.md` — guide page → requirement → implementation / adaptation.
- `EVIDENCE_LEDGER.md` — experiment IDs, dataset versions, exact commands, measured results.
- `USER_ACTIONS.md` — the short list of things only Ihsan can do.
- `AWS_COST_PLAN.md` — cost sheet for project 3 (drafted before any cloud resource is created).

Build order was chosen by us (#6 → #1 → #15); the guide does not mandate an order.
