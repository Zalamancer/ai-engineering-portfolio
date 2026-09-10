# Corpus manifest — "web platform team" documentation set

Public technical documentation standing in for a company's internal docs. All
sources allow redistribution; raw files are stored unmodified under `data/raw/`.

| collection | source | pinned version (git commit) | fetched | format | license |
|---|---|---|---|---|---|
| fastapi | https://github.com/fastapi/fastapi (docs/en/docs) | `50113da16fec53b66b80d75e80a89296de4fa5a5` (2026-09-01) | 2026-09-09 | markdown (155 files) | MIT |
| starlette | https://github.com/encode/starlette (docs/) | `f03f65c2f98c592773d691b4d309c68b83e568ef` (2026-09-07) | 2026-09-09 | markdown (25 files) | BSD-3-Clause |
| uvicorn | https://github.com/encode/uvicorn (docs/) | `fa324a415364563cf45908966435e2480a6b46bf` (2026-09-09) | 2026-09-09 | markdown (16 files) | BSD-3-Clause |
| rfc | https://www.rfc-editor.org/rfc/rfc9110.pdf — HTTP Semantics | RFC 9110 (June 2022) | 2026-09-09 | PDF (311 pages) | IETF Trust (unmodified redistribution permitted) |
| rfc | https://www.rfc-editor.org/rfc/rfc9112.txt — HTTP/1.1 | RFC 9112 (June 2022) | 2026-09-09 | plain text | IETF Trust |
| rfc | https://www.rfc-editor.org/rfc/rfc9457.txt — Problem Details for HTTP APIs | RFC 9457 (July 2023) | 2026-09-09 | plain text | IETF Trust |
| rfc | https://www.rfc-editor.org/rfc/rfc6455.html — The WebSocket Protocol | RFC 6455 (Dec 2011) | 2026-09-09 | HTML | IETF Trust |
| rfc | https://www.rfc-editor.org/rfc/rfc6265.html — HTTP State Management (Cookies) | RFC 6265 (Apr 2011) | 2026-09-09 | HTML | IETF Trust |

Why this corpus: FastAPI, Starlette and Uvicorn are one coherent stack (the
web framework, the ASGI toolkit under it, and the server that runs it), which is
what an internal platform-team wiki would look like. The HTTP/WebSocket/cookie
RFCs are the reference material such a team would keep beside it. Together they
give the four formats the guide asks the loader to accept (markdown, text, HTML,
PDF), plenty of exact identifiers (setting names, header names, status codes)
that reward keyword search, and cross-document questions (e.g. a Uvicorn flag
whose meaning is defined in an RFC).

Re-fetch: `scripts/fetch_corpus.sh` (re-clones at the pinned commits).
Note: the RFC HTML/text/PDF files are chunked for retrieval; the RFCs themselves
are never edited or redistributed in modified form.
