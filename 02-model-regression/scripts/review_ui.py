"""Human review screen for the golden dataset (guide Phase 2 requires hand-verified labels).
    uv run streamlit run scripts/review_ui.py
Edit the category / summary / difficulty if wrong, then press Verified. Nothing counts as
ground truth until this has been done; runs record how many cases were verified."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from regress.config import settings  # noqa: E402
from regress.dataset import GoldenDataset, Verification  # noqa: E402
from regress.feature import CATEGORIES  # noqa: E402

st.set_page_config(page_title="Review golden dataset", layout="wide")
st.title("Review the golden support-email dataset")
st.caption("Categories: billing = money · technical = something is broken · account = access/identity · general = everything else. "
           "You decide; the AI draft is only a suggestion.")

ds = GoldenDataset.load(settings.golden_path)
counts = ds.counts()
with st.sidebar:
    st.metric("Cases", counts["total"])
    for k, v in counts["by_status"].items():
        st.metric(k, v)
    show = st.multiselect("Show status", sorted(counts["by_status"]), default=[s for s in counts["by_status"] if s != "human_verified"] or list(counts["by_status"]))
    reviewer = st.text_input("Your name", value="Ihsan")

visible = [c for c in ds.cases if c.verification.status in show]
if not visible:
    st.success("Nothing left in this filter."); st.stop()
i = st.number_input("Case #", 1, len(visible), 1) - 1
c = visible[i]
st.subheader(f"{c.id} · {c.expected_difficulty} · tags: {', '.join(c.tags) or '–'} · {c.verification.status}")
st.text_area("Email (read-only)", c.input, height=120, disabled=True)
cat = st.radio("Correct category", CATEGORIES, index=CATEGORIES.index(c.expected_category), horizontal=True, key=f"cat_{c.id}")
summary = st.text_area("Ideal one-sentence summary", c.expected_summary, height=80, key=f"sum_{c.id}")
diff = st.select_slider("Difficulty", ["easy", "medium", "hard"], value=c.expected_difficulty, key=f"diff_{c.id}")
notes = st.text_input("Why this case matters / notes", c.notes, key=f"notes_{c.id}")
b1, b2, b3 = st.columns(3)


def _apply():
    c.expected_category, c.expected_summary, c.expected_difficulty, c.notes = cat, summary.strip(), diff, notes.strip()


if b1.button("✅ Verified", type="primary"):
    _apply(); c.verification = Verification(status="human_verified", verified_by=reviewer, verified_at=time.strftime("%Y-%m-%d"))
    ds.save(settings.golden_path); st.rerun()
if b2.button("💾 Save edits (still unverified)"):
    _apply(); ds.save(settings.golden_path); st.rerun()
if b3.button("🗑 Reject"):
    c.verification = Verification(status="rejected", verified_by=reviewer, verified_at=time.strftime("%Y-%m-%d"))
    ds.save(settings.golden_path); st.rerun()
st.caption("Saving changes the dataset fingerprint; the version string in data/golden/golden.json should be bumped (e.g. 0.2.0-reviewed) once a review pass is complete.")
