# Requirements checklist — guide project #6 (pp. 20–23) → implementation

Status: ✅ implemented + evidence · 🟡 implemented, limitation noted · ⚪ optional / stretch · ❌ not done

| # | Guide requirement (page) | Status | Where / evidence | Adaptation or limitation |
|---|---|---|---|---|
| 1.1 | Multi-format loader: markdown, text, HTML, PDF; metadata source file, section heading, page number; store raw + processed (p.20) | ✅ | `hybrid_rag/loaders.py`; `data/raw/` unmodified, `data/processed/docs.jsonl`; tests `test_loaders_chunking.py` | PDF: pypdf drops inline BCP 14 keywords in RFC 9110 (see README failure analysis) |
| 1.2 | Three switchable chunking strategies: fixed+overlap, recursive by headers, semantic by embedding similarity; track strategy per chunk (p.20–21) | ✅ | `hybrid_rag/chunking.py`, `Chunk.strategy`; indexes per strategy under `data/index/<strategy>/` | — |
| 1.3 | Embed every chunk (text-embedding-3-small) into ChromaDB with metadata; BM25 in parallel; indexes in sync (p.21) | 🟡 | `hybrid_rag/index.py`; `IndexBundle.check_sync()`; `test_indexes_in_sync` | **Model substitution:** BAAI/bge-small-en-v1.5 (local, MIT) instead of OpenAI embeddings — no paid API authorised. Recorded in each `manifest.json` |
| 1.4 | Deduplication: cosine > 0.95 → flag and skip (p.21) | ✅ | `dedup_filter()`; `data/index/*/dedup_log.json` (16 / 108 / 23 skipped for fixed / recursive / semantic) | Documented false positives on templated FastAPI pages |
| 2.1 | Dense retrieval top-k by cosine, k=10 (p.21) | ✅ | `Retriever.dense`, `RAG_DENSE_TOP_K=10` | — |
| 2.2 | Sparse BM25 retrieval top-k (p.21) | ✅ | `Retriever.sparse`, custom tokenizer for identifiers | — |
| 2.3 | Reciprocal Rank Fusion with configurable weighting e.g. 0.7/0.3 (p.21) | ✅ | `reciprocal_rank_fusion()`, `RAG_RRF_DENSE_WEIGHT/SPARSE_WEIGHT` | Weight sweep shows weights are inert when all 20 candidates are reranked |
| 2.4 | Cross-encoder reranker over top 20, keep top 5 (p.21) | ✅ | `Reranker` (cross-encoder/ms-marco-MiniLM-L-6-v2), `rerank_candidates=20`, `final_top_k=5` | Small local model |
| 3.1 | Grounded prompt: answer only from context, [n] citations, say when insufficient; numbered context blocks (p.21) | ✅ | `generation.SYSTEM_PROMPT`, `build_context()` | Adds an explicit `ambiguous` status |
| 3.2 | Citation verification: does [n] support the claim? LLM-as-judge per pair; flag unsupported (p.21) | ✅ | `verify_claims()`; flags `unsupported_citation`, `uncited_claim`, `invalid_citation_numbers`; tests | Judge = same local model |
| 3.3 | Confidence scorer: retrieval confidence, citation coverage, completeness → composite (p.21–22) | ✅ | `retrieval_confidence()`, `Answer.confidence` | Weights 0.4/0.4/0.2 are a design choice, not tuned |
| 3.4 | "I don't know": below threshold, return what was found / not found / documents to check (p.22) | ✅ | `not_found_response()`, threshold tuned on dev split (0.40) | — |
| 4.1 | Golden Q&A dataset, 50+ hand-written pairs tied to sections: lookups, multi-hop, no-answer, ambiguous (p.22) | 🟡 | `eval/questions.json`: 75 items (51 lookup, 8 multi-hop, 8 no-answer, 8 ambiguous), each with verbatim evidence quotes; `scripts/check_questions.py` | **Drafted by AI, labelled `ai_generated`; human verification pending** via `scripts/review_ui.py`. Dev/held-out split added (44/31) |
| 4.2 | Automated metrics: answer correctness (judge vs gold), faithfulness, retrieval relevance, citation accuracy; run on every change (p.22) | ✅ | `hybrid_rag/evaluation.py`, `scripts/run_eval.py answers`; per-run `summary.json` | Judge is the local model; "run on every change" = manual command, no CI here |
| 4.3 | Chunking-strategy comparison report (p.22) | ✅ | `scripts/run_eval.py retrieval` (18 configs) + answer runs per strategy; `eval/results/RESULTS.md` | — |
| 5.1 | FastAPI: POST /v1/ask, GET /v1/documents, POST /v1/ingest, OpenAPI docs (p.22) | ✅ | `hybrid_rag/api.py` (+ `/v1/retrieve`, `/health`) | `/v1/ingest` rebuilds synchronously |
| 5.2 | Dashboard: answer with citations, ranked chunks, confidence breakdown, hybrid-vs-dense toggle (p.22) | ✅ | `hybrid_rag/ui.py` (Streamlit) | — |
| 5.3 | Docker-compose with API, ChromaDB, frontend + seed script (p.22) | 🟡 | `Dockerfile`, `docker-compose.yml` (api, ui, seed profile) | ChromaDB embedded (file-based option) rather than a separate container; LLM on host. **Not built on this Mac (disk)** |
| 6.1 | Demo walkthrough < 4 min (p.22) | ⚪ | Script in README "Demo script" | Recording is a human task |
| 6.2 | Case study with numbers (p.23) | 🟡 | README "Results" + `RESULTS.md` | Numbers are measured but rest on an unverified question set and a model judge |
| + | Prompt requirement: compare configurations against a plain baseline | ✅ | baseline = fixed / dense-only / no rerank, marked in every table | — |
| + | Prompt requirement: evaluate retrieval and answer quality separately | ✅ | `retrieval_eval.json` (no LLM) vs `runs/*/summary.json` | — |
| + | Prompt requirement: dev vs held-out questions | ✅ | `split` field; sweeps use dev only; tables report held-out separately | Both splits drafted by the same AI process |
