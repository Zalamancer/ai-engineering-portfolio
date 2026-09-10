# 01 · Hybrid-search RAG over a web-platform documentation corpus

Guide project #6 (BASWE "15 AI Engineering Projects", pp. 20–23): a retrieval-augmented
question-answering service over "internal" technical documentation, with **hybrid retrieval
(BM25 + dense vectors fused with Reciprocal Rank Fusion), cross-encoder reranking, grounded
generation with numbered citations, claim-level citation verification, an explicit
"insufficient evidence" path, and an evaluation suite that compares retrieval configurations
and chunking strategies against a plain baseline.**

Everything runs locally on a Mac with free models. No paid API is used.

## What is in the box

```
hybrid_rag/
  loaders.py      markdown / text / HTML / PDF → normalised text + section/page metadata
  chunking.py     three switchable strategies: fixed, recursive (structure-aware), semantic
  embeddings.py   bge-small-en-v1.5 embedder + ms-marco MiniLM cross-encoder (local)
  index.py        ChromaDB (dense) + BM25 (sparse) built from the same chunks; near-dup filter
  retrieval.py    dense / sparse / hybrid (weighted RRF) → rerank → retrieval confidence
  generation.py   grounded prompt, [n] citation parsing, claim verification, confidence, "I don't know"
  evaluation.py   gold-evidence matching, LLM-as-judge correctness / faithfulness
  pipeline.py     RAGPipeline.ask() / .retrieve()
  api.py          FastAPI: POST /v1/ask, GET /v1/retrieve, GET /v1/documents, POST /v1/ingest, /docs
  ui.py           Streamlit dashboard with hybrid-vs-dense side-by-side toggle
scripts/
  fetch_corpus.sh      re-fetch the corpus at the pinned commits
  ingest.py            parse + chunk + embed + index (all strategies)
  serve_llm.sh         start the local LLM server (mlx_lm, Apple silicon)
  run_eval.py          retrieval eval · dev-split sweeps · answer-quality runs
  run_all_answer_evals.sh  the six configurations compared in the results
  compare.py           → eval/results/RESULTS.md and FAILURES.md
  review_ui.py         human review screen for the question set
  check_questions.py   verifies every evidence quote exists in the corpus
eval/questions.json    75 questions (lookup / multi-hop / no-answer / ambiguous), dev + held-out splits
eval/results/          measured results (JSON + markdown)
data/raw/MANIFEST.md   corpus provenance, versions, licences
tests/                 20 unit/integration tests (pytest)
```

## Corpus

FastAPI, Starlette and Uvicorn documentation (one coherent web stack — the kind of wiki a
platform team keeps) plus five HTTP / WebSocket / cookie RFCs as the reference material next
to it. 198 documents, ~2.1 M characters, four formats (193 markdown, 2 plain text, 2 HTML,
1 PDF of 311 pages). Sources, pinned commits and licences: [`data/raw/MANIFEST.md`](data/raw/MANIFEST.md).

## Setup (macOS, Apple silicon)

```bash
cd 01-hybrid-rag
uv sync                                  # Python 3.12 env (uv installs the interpreter if needed)
./scripts/fetch_corpus.sh                # ~40 MB of docs at the pinned commits (already present in this checkout)
uv run python scripts/ingest.py          # builds fixed / recursive / semantic indexes (~3 min on an M4)
./scripts/serve_llm.sh                   # local LLM on :8081 (downloads ~2.3 GB once); keep it running
uv run uvicorn hybrid_rag.api:app --port 8000      # API + OpenAPI docs at http://127.0.0.1:8000/docs
uv run streamlit run hybrid_rag/ui.py              # dashboard
uv run pytest -q                                   # tests
```

Configuration is via environment variables (`RAG_*`), see [`.env.example`](.env.example).
To use OpenAI (or any OpenAI-compatible endpoint) instead of the local model, set
`RAG_LLM_BASE_URL`, `RAG_LLM_API_KEY`, `RAG_LLM_MODEL` — no code changes.

Docker: `Dockerfile` + `docker-compose.yml` package the API and UI (the LLM stays on the host
or any endpoint). **They were written but not built on this Mac** — the machine had ~2 GB of
free disk when this was done, less than the torch image needs. See limitations.

## Architecture

```
 raw files ──► loaders (normalise, keep # headings, page offsets) ──► docs.jsonl
                                                                        │
              ┌─────────── per chunking strategy (fixed | recursive | semantic) ───────────┐
              │  chunks ──► bge-small embeddings ──► near-dup filter (cos > 0.95) ──► Chroma │
              │                                   └────────────────────────────────► BM25   │
              └─────────────────────────────────────────────────────────────────────────────┘
 question ──► dense top-10 ─┐
          └─► BM25  top-10 ─┴─► weighted RRF (0.7 / 0.3) ──► cross-encoder rerank top-20 ──► top-5
                                                                        │
                    retrieval confidence < 0.40 ──► structured "not found" (what was found, where to look)
                                                                        │
              grounded generation (STATUS answered|insufficient|ambiguous + [n] citations)
                                                                        │
              split into claims ──► each (claim, cited passage) → judge SUPPORTED / PARTIAL / NOT_SUPPORTED
              completeness judge ──► confidence = 0.4·retrieval + 0.4·citation coverage + 0.2·completeness
```

Design decisions worth discussing:

- **One text convention for four formats.** Every loader emits plain text with markdown
  `#` headings (RFC section numbers become headings; PDF page starts are recorded as offsets).
  Section and page metadata are then *resolved from the character span*, so no chunker has to
  know about formats.
- **Both indexes from one chunk list.** Chroma and BM25 are built from the same deduplicated
  list in the same order; `IndexBundle.check_sync()` is exposed on `/v1/documents` and covered
  by a test.
- **Tokeniser for technical docs.** BM25 keeps compound identifiers (`Sec-WebSocket-Key`,
  `--proxy-headers`, `pydantic.BaseSettings`) as single tokens *and* emits their parts.
- **Citation verification checks support, not existence.** Each sentence of the answer is a
  claim; each `[n]` is checked against the passage text by a judge prompt. Uncited claims,
  unsupported citations and citation numbers that don't exist are all flagged separately.
- **Abstention is decided before generation.** The retrieval-confidence threshold (0.40) was
  chosen on the dev split only; the held-out split is reported separately.
- **Ambiguity is a first-class status.** The generation prompt asks the model to name
  interpretations instead of silently picking one; the eval scores whether it did.

## Results

Measured on this Mac with the local models named in the tables. See
[`eval/results/RESULTS.md`](eval/results/RESULTS.md) for the full tables and
[`eval/results/FAILURES.md`](eval/results/FAILURES.md) for saved failure examples.
The summary below is filled in from those files.

RESULTS_SUMMARY_PLACEHOLDER

**Read the numbers with these caveats.** (1) The 75 questions were drafted by an AI reading
the corpus and are **not yet human-verified** (status in `eval/questions.json`). Questions
written from the text tend to reuse its exact words, which favours keyword search. (2) The
generator *and* the judge are the same local 4B model; judge verdicts are model opinions, not
human ones. (3) The corpus is small (≈3–4 k chunks); results will not transfer to a 100× larger
corpus without re-measuring.

## Failure analysis

See [`eval/results/FAILURES.md`](eval/results/FAILURES.md) (auto-extracted per run). Recurring
patterns observed while building:

- **Near-duplicate filter false positives.** FastAPI's docs are templated: `response-headers.md`
  and `response-cookies.md` share whole paragraphs, so the 0.95 cosine filter dropped a
  *headers* passage as a duplicate of a *cookies* passage (see `data/index/*/dedup_log.json`).
  The guide's threshold is kept, and the log makes the trade-off visible.
- **PDF extraction loses inline RFC keywords.** In the RFC 9110 PDF the BCP 14 words
  (MUST/SHOULD/MAY) are typeset separately and pypdf emits them at the end of the paragraph,
  so "The server MUST send…" becomes "The server  send…". Questions about normative strength
  in the PDF are affected; the plain-text RFCs do not have this problem.
- **Uncited first sentence.** The 4B model sometimes cites only the last sentence of a
  two-sentence answer; the first sentence is then flagged `uncited_claim` and lowers coverage
  even when it is correct. This is what the verification layer is for, but it also means
  coverage penalises style as well as substance.
- **RRF weights are inert when everything gets reranked.** With 10 + 10 candidates and a
  reranker over the top 20, the dense/sparse weight cannot change the outcome; it only matters
  with reranking off (measured in the sweep).

## Limitations (honest list)

- Local 4B generator instead of the guide's GPT-4o / Claude Sonnet; answers are shorter and
  citation discipline is weaker than a frontier model would give.
- Judge = generator model; no human calibration of the judge yet.
- Question set not human-verified; dev/held-out split exists but the held-out set was written
  by the same process.
- Docker image not built here (disk); `/v1/ingest` rebuilds an index synchronously (fine for
  this corpus size, not for a large one).
- Semantic chunking uses the same small embedding model as retrieval; no separate tuning.

## Demo script (≈3 minutes)

1. `./scripts/serve_llm.sh` in one terminal, `uv run streamlit run hybrid_rag/ui.py` in another.
2. Ask *"What does --proxy-headers do in Uvicorn?"* — show the answer, the `[n]` citations,
   the claim-by-claim verification and the confidence breakdown.
3. Tick **Compare hybrid vs dense-only** and ask *"How does a WebSocket server compute
   Sec-WebSocket-Accept?"* — exact identifiers are where BM25 helps dense retrieval.
4. Ask *"How do I configure the retry policy for Celery workers?"* — the system abstains and
   lists the closest passages and documents to check manually.
5. Ask *"What is the default timeout?"* — ambiguity handling: interpretations instead of a guess.
6. Open `eval/results/RESULTS.md` and walk through baseline vs hybrid vs BM25-only and the
   chunking comparison; open `FAILURES.md` for one concrete failure.
