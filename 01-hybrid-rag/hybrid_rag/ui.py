"""Streamlit query dashboard (guide Phase 5.2): answer with clickable citations, ranked
chunks, confidence breakdown, and a hybrid-vs-dense side-by-side toggle.

    uv run streamlit run hybrid_rag/ui.py
"""
from __future__ import annotations

import json

import streamlit as st

from hybrid_rag.pipeline import get_pipeline

st.set_page_config(page_title="Hybrid RAG — web platform docs", layout="wide")
st.title("Hybrid RAG over FastAPI / Starlette / Uvicorn / HTTP RFC docs")

p = get_pipeline()
with st.sidebar:
    st.header("Retrieval settings")
    strategy = st.selectbox("Chunking index", p.strategies(), index=p.strategies().index(p.s.default_strategy) if p.s.default_strategy in p.strategies() else 0)
    mode = st.radio("Retrieval mode", ["hybrid", "dense", "sparse"], horizontal=True)
    rerank = st.checkbox("Cross-encoder rerank", value=True)
    verify = st.checkbox("Verify citations (LLM judge)", value=True)
    top_k = st.slider("Passages given to the model", 1, 10, p.s.final_top_k)
    compare = st.checkbox("Compare hybrid vs dense-only side by side", value=False)
    st.caption(f"LLM: `{p.s.llm_model}` — {'online' if p.llm.is_available() else 'OFFLINE (start scripts/serve_llm.sh)'}")
    st.caption(f"Embeddings: `{p.s.embedding_model}` · Reranker: `{p.s.reranker_model}`")

question = st.text_input("Ask a question about the documentation", placeholder="e.g. What does --proxy-headers do in Uvicorn?")


def render_answer(ans: dict, col):
    with col:
        badge = {"answered": "🟢", "insufficient": "🟠", "ambiguous": "🟡"}.get(ans["status"], "⚪")
        st.subheader(f"{badge} {ans['status']}")
        st.markdown(ans["answer"])
        if ans.get("not_found"):
            with st.expander("What was found / where to look manually", expanded=True):
                st.json(ans["not_found"])
        c = ans["confidence"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Composite", f"{c['composite']:.2f}")
        m2.metric("Retrieval", f"{c['retrieval']:.2f}")
        m3.metric("Citation coverage", f"{c['citation_coverage']:.2f}")
        m4.metric("Completeness", f"{c['completeness']:.2f}")
        if ans["flags"]:
            st.warning("Flags: " + "; ".join(ans["flags"]))
        if ans["citations"]:
            st.markdown("**Citations**")
            for cit in ans["citations"]:
                page = f", p.{cit['page']}" if cit["page"] else ""
                st.markdown(f"[{cit['n']}] [{cit['doc_id']}]({cit['source_url']}) — {cit['section']}{page}")
        if ans["claims"]:
            with st.expander("Claim-by-claim citation verification"):
                for cl in ans["claims"]:
                    ok = "✅" if cl["supported"] else ("⚠️ uncited" if not cl["citations"] else "❌")
                    st.markdown(f"{ok} {cl['claim']}  \n<small>{json.dumps(cl['verdicts'])}</small>", unsafe_allow_html=True)
        with st.expander(f"Retrieved passages ({ans['retrieval']['mode']}, {ans['retrieval']['strategy']}, reranked={ans['retrieval']['reranked']})"):
            for h in ans["retrieval"]["hits"]:
                st.markdown(f"**[{h['rank']}]** `{h['doc_id']}` — {h['section']}  "
                            f"<small>rerank={h['rerank_score']} dense#={h['dense_rank']} bm25#={h['sparse_rank']} rrf={h['rrf_score']}</small>",
                            unsafe_allow_html=True)
                st.code(h["text"][:700] + ("…" if len(h["text"]) > 700 else ""))
        st.caption(f"timings ms: {ans['timings_ms']} · usage: {ans['usage']} · model: {ans['model']}")


if question:
    if compare:
        c1, c2 = st.columns(2)
        with st.spinner("hybrid …"):
            a1 = p.ask(question, strategy, "hybrid", rerank, verify, top_k).to_dict()
        with st.spinner("dense-only …"):
            a2 = p.ask(question, strategy, "dense", rerank, verify, top_k).to_dict()
        c1.markdown("### Hybrid (BM25 + dense, RRF)")
        c2.markdown("### Dense only")
        render_answer(a1, c1)
        render_answer(a2, c2)
    else:
        with st.spinner("retrieving + generating …"):
            a = p.ask(question, strategy, mode, rerank, verify, top_k).to_dict()
        render_answer(a, st.container())
