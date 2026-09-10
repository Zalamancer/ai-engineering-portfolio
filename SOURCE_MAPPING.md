# Source mapping — guide pages → requirements → implementation / adaptation

Primary blueprint: `BASWE_15_AI_Engineering_Projects_Guide.pdf` (61 pages). Supporting PDFs
(`BASWE_Build_These_Six_Projects.pdf`, `baswe-six-project-build-guide.pdf`) were read for
context only; none of their projects (Knowledge Graph RAG, Fieldnote, Casefile, Groundtruth,
Human Calibration, …) were substituted in.

The guide's marketing copy, community invitations and job/salary claims were treated as
non-instructions.

## Project #6 — RAG Pipeline with Hybrid Search Over Internal Docs (pp. 20–23) → `01-hybrid-rag/`

Detailed per-requirement table: [`01-hybrid-rag/REQUIREMENTS_CHECKLIST.md`](01-hybrid-rag/REQUIREMENTS_CHECKLIST.md).

| Guide element | Guide says | What we did | Why it differs |
|---|---|---|---|
| Corpus | "a company's internal documentation" | FastAPI + Starlette + Uvicorn docs at pinned commits + 5 RFCs (MD/TXT/HTML/PDF) | Prompt asked for a public, licensed stand-in; this set is one coherent web stack with exact identifiers that exercise keyword search and cross-document questions |
| Embeddings (p.20) | OpenAI text-embedding-3-small | BAAI/bge-small-en-v1.5, local | No paid API authorised for this project; interface allows swapping (indexes must be rebuilt) |
| LLM (p.20) | GPT-4o or Claude Sonnet | Qwen3-4B-Instruct-2507 (Apache-2.0) via local mlx_lm server, OpenAI-compatible | Same reason; noticeably weaker model — labelled in every result |
| Vector store (p.20) | ChromaDB or Qdrant | ChromaDB, persistent/embedded | Guide's own option |
| Reranker (p.21) | cross-encoder or LLM-as-judge | cross-encoder/ms-marco-MiniLM-L-6-v2, local | Cheaper and deterministic |
| Golden Q&A (p.22) | 50+ pairs "by hand" | 75 pairs drafted by AI with verbatim evidence quotes; review UI for a human to verify | Prompt allows AI drafting but requires labelling until a person verifies — they are labelled `ai_generated` |
| Statuses | answer or "I don't know" | answered / insufficient / ambiguous | Prompt requires explicit handling of ambiguous questions |
| Docker compose (p.22) | API + ChromaDB + frontend | API + UI (+ seed profile); ChromaDB embedded in API; LLM on host | Compose written, **not built** here (≈2–3 GB free disk) |
| Everything else | as written | as written | — |

## Project #1 — Model Regression Detection System (pp. 3–5) → `02-model-regression/`

Not started. Planned adaptations already known from the prompt: the guide's "statistical
significance" thresholds (3 % / 8 %) will be implemented as *policy thresholds* and named so;
sample counts and uncertainty will be recorded; LLM-as-judge summary scores are model
judgments; Slack delivery stays pending until a test destination is authorised; model access
uses whatever supported endpoint is available (local by default).

## Project #15 — Agent Orchestration System (pp. 56–59) → `03-agent-orchestration/`

Not started. AWS is hosting/storage/monitoring only; LangGraph stays the orchestrator. See
`AWS_COST_PLAN.md` for the (not yet priced) cost sheet.
