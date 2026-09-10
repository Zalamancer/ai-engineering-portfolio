"""Human review screen for eval/questions.json (guide Phase 4.1 requires hand-verified Q&A).

    uv run streamlit run scripts/review_ui.py

For each AI-drafted question you see the question, the proposed answer, and the exact
source passage. Fix anything wrong, then press "Verified". Items stay 'ai_generated'
until a person does this — the eval reports show the verification counts.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hybrid_rag.config import settings  # noqa: E402
from hybrid_rag.loaders import read_processed  # noqa: E402

QPATH = Path(__file__).resolve().parent.parent / "eval" / "questions.json"

st.set_page_config(page_title="Review eval questions", layout="wide")
st.title("Review the evaluation questions")
st.caption("You are the ground truth. Correct anything wrong before pressing Verified; do not approve blindly.")


@st.cache_data
def load_docs():
    return {d.doc_id: d.text for d in read_processed(settings.processed_dir / "docs.jsonl")}


def load_q():
    return json.loads(QPATH.read_text())


def save_q(data):
    data["last_reviewed"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    QPATH.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def passage(doc_text: str, quote: str, window: int = 500) -> str:
    q = re.sub(r"\s+", " ", quote).strip().lower()
    flat = re.sub(r"\s+", " ", doc_text)
    i = flat.lower().find(q)
    if i == -1:
        return "(quote not found in current document text)"
    return "…" + flat[max(0, i - window): i + len(q) + window] + "…"


data = load_q()
docs = load_docs()
qs = data["questions"]
statuses = sorted({q["verification"]["status"] for q in qs})
with st.sidebar:
    st.metric("Total", len(qs))
    for s in statuses:
        st.metric(s, sum(1 for q in qs if q["verification"]["status"] == s))
    flt = st.multiselect("Show status", statuses, default=[s for s in statuses if s != "human_verified"] or statuses)
    reviewer = st.text_input("Your name (recorded as verified_by)", value="Ihsan")

visible = [q for q in qs if q["verification"]["status"] in flt]
if not visible:
    st.success("Nothing left to review in this filter.")
    st.stop()

idx = st.number_input("Question #", 1, len(visible), 1) - 1
q = visible[idx]
st.subheader(f"{q['id']} · {q['type']} · {q['split']} split · status: {q['verification']['status']}")

new_question = st.text_area("Question", q["question"], height=70)
new_gold = st.text_area("Correct answer (edit if wrong)", q["gold_answer"], height=110)
new_type = st.selectbox("Type", list(data["types"]), index=list(data["types"]).index(q["type"]))
new_notes = st.text_input("Notes", q.get("notes", ""))

st.markdown("**Evidence passages from the source documents**")
if not q["evidence"]:
    st.info("No evidence: this question is expected to be unanswerable or ambiguous.")
for ev in q["evidence"]:
    st.markdown(f"`{ev['doc_id']}` — quote: *{ev['quote']}*")
    st.code(passage(docs.get(ev["doc_id"], ""), ev["quote"]), language=None)

c1, c2, c3 = st.columns(3)
if c1.button("✅ Verified (save edits)", type="primary"):
    q.update({"question": new_question.strip(), "gold_answer": new_gold.strip(), "type": new_type, "notes": new_notes.strip()})
    q["verification"] = {"status": "human_verified", "verified_by": reviewer, "verified_at": time.strftime("%Y-%m-%d")}
    save_q(data)
    st.success("saved"); st.rerun()
if c2.button("💾 Save edits, keep unverified"):
    q.update({"question": new_question.strip(), "gold_answer": new_gold.strip(), "type": new_type, "notes": new_notes.strip()})
    save_q(data)
    st.success("saved"); st.rerun()
if c3.button("🗑 Reject (exclude from eval)"):
    q["verification"] = {"status": "rejected", "verified_by": reviewer, "verified_at": time.strftime("%Y-%m-%d")}
    save_q(data)
    st.warning("rejected"); st.rerun()
