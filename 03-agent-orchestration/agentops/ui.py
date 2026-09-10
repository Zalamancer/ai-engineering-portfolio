"""Streamlit operator console: runs & progress, pending approvals (approve / modify / reject / take over),
results, execution trace tree, memory dashboard, usage ledger.   uv run streamlit run agentops/ui.py"""
from __future__ import annotations

import json
import time

import streamlit as st

from agentops.config import settings
from agentops.db import DB

st.set_page_config(page_title="agentops console", layout="wide")
db = DB(settings.db_path)
st.title("Agent orchestration console")
st.caption(f"db: {settings.db_path} · budgets: steps {settings.max_steps} · llm calls {settings.max_llm_calls} · tool calls {settings.max_tool_calls} · "
           f"tokens {settings.max_tokens_total} · wall {settings.max_wall_seconds}s · run cost ${settings.max_cost_usd} · app allowance ${settings.app_allowance_usd}")

tab_runs, tab_appr, tab_mem, tab_ledger = st.tabs(["Runs & traces", "Approvals", "Memory", "Ledger"])

with tab_runs:
    with st.form("new_run"):
        req = st.text_area("New request", "Research how Uvicorn and FastAPI handle proxy headers and HTTPS termination, count how many documentation sections mention proxies, and post a short cited report to the team webhook.")
        need_plan = st.checkbox("Require human approval of the plan before any work starts", value=False)
        if st.form_submit_button("Submit run"):
            rid = db.create_run(req, {"require_plan_approval": need_plan, "user_id": "default"},
                                {k: getattr(settings, k) for k in ("max_steps", "max_llm_calls", "max_tool_calls", "max_tokens_total", "max_wall_seconds", "max_cost_usd")})
            db.event(rid, "submitted", "ui", {"request": req})
            st.success(f"submitted {rid} — a worker (python -m agentops.worker) will pick it up")
    runs = db.list_runs(30)
    if not runs:
        st.info("no runs yet"); st.stop()
    labels = {f"{r['run_id']} · {r['status']} · {r['request'][:60]}": r["run_id"] for r in runs}
    pick = st.selectbox("Run", list(labels))
    run = db.get_run(labels[pick])
    badge = {"completed": "🟢", "failed": "🔴", "paused_for_approval": "🟡", "paused_budget": "🟠"}.get(run["status"], "🔵")
    st.subheader(f"{badge} {run['status']}  —  {run['run_id']}")
    if run.get("error"):
        st.error(run["error"])
    tasks = db.tasks(run["run_id"])
    if run.get("plan"):
        st.markdown(f"**Plan** (supervisor confidence {run['plan']['confidence']:.2f}): {run['plan'].get('rationale', '')}")
    if tasks:
        done = sum(1 for t in tasks if t["status"] == "done")
        st.progress(done / len(tasks), text=f"{done}/{len(tasks)} tasks done")
        for t in tasks:
            icon = {"done": "✅", "failed": "❌", "running": "⏳", "review": "🔍", "rejected": "↩️"}.get(t["status"], "▫️")
            with st.expander(f"{icon} {t['idx']}. {t['title']} — {t['specialist']} · {t['status']} · attempts {t['attempts']} · review rounds {t['review_rounds']}"):
                st.write(t["description"])
                if t.get("output"):
                    st.markdown("**Output**"); st.json(t["output"])
                if t.get("review"):
                    st.markdown("**Reviewer**"); st.json(t["review"])
                if t.get("error"):
                    st.error(t["error"])
    if run.get("result"):
        st.markdown("### Result")
        st.markdown(run["result"].get("report", ""))
        st.markdown("**Citations:** " + ", ".join(run["result"].get("citations", [])))
        if run["result"].get("caveats"):
            st.warning("Caveats: " + "; ".join(run["result"]["caveats"]))
    st.markdown("### Execution trace")
    ev = db.events(run["run_id"])
    tot = {"llm_calls": sum(1 for e in ev if e["kind"] == "llm_call"), "tool_calls": sum(1 for e in ev if e["kind"] == "tool_call"),
           "tokens_in": sum(e["tokens_in"] or 0 for e in ev), "tokens_out": sum(e["tokens_out"] or 0 for e in ev),
           "cost_usd": round(sum(e["cost_usd"] or 0 for e in ev), 6), "wall_s": round(ev[-1]["ts"] - ev[0]["ts"], 1) if ev else 0}
    st.caption(json.dumps(tot))
    colour = {"ok": "🟩", "warning": "🟨", "error": "🟥", "paused": "🟧", "replayed": "🟦"}
    by_task = {None: []}
    for e in ev:
        by_task.setdefault(e["task_id"], []).append(e)
    names = {t["task_id"]: f"{t['idx']}. {t['title']}" for t in tasks}
    for tid, evs in by_task.items():
        st.markdown(f"**{names.get(tid, 'run level')}**")
        for e in evs:
            lat = f" · {e['latency_ms']:.0f} ms" if e["latency_ms"] else ""
            tok = f" · {e['tokens_in']}→{e['tokens_out']} tok" if e["tokens_in"] else ""
            with st.expander(f"{colour.get(e['status'], '⬜')} {time.strftime('%H:%M:%S', time.localtime(e['ts']))} {e['kind']} · {e['agent']}{lat}{tok}"):
                st.json(e["payload"])

with tab_appr:
    pend = db.approvals(status="pending")
    st.subheader(f"{len(pend)} pending approval(s)")
    for a in pend:
        st.markdown(f"**{a['level']}** — run `{a['run_id']}` · {a['reason']}")
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("Proposed action / plan:"); st.json(a["proposed"])
        with c2:
            st.markdown("Context:"); st.json({k: a["context"].get(k) for k in ("request", "completed", "memories")})
        by = st.text_input("Your name", "Ihsan", key=f"by{a['approval_id']}")
        mod = st.text_area("Modified plan/args JSON (for Modify) or content (for Take over)", "", key=f"m{a['approval_id']}")
        b1, b2, b3, b4 = st.columns(4)

        def _resolve(status, action, extra=None):
            d = {"action": action, "by": by, **(extra or {})}
            db.resolve_approval(a["approval_id"], status, d, by)
            db.update_run(a["run_id"], status="resuming")
            db.event(a["run_id"], "approval_ui", by, {"approval_id": a["approval_id"], "action": action})
            st.rerun()
        if b1.button("✅ Approve", key=f"a{a['approval_id']}"):
            _resolve("approved", "approve")
        if b2.button("✏️ Modify", key=f"mo{a['approval_id']}"):
            try:
                obj = json.loads(mod)
            except Exception:
                st.error("Modify needs valid JSON"); obj = None
            if obj is not None:
                _resolve("modified", "modify", {"plan": obj} if a["level"] == "approve_plan" else {"args": obj})
        if b3.button("❌ Reject", key=f"r{a['approval_id']}"):
            _resolve("rejected", "reject")
        if b4.button("🧑 Take over", key=f"t{a['approval_id']}"):
            _resolve("taken_over", "take_over", {"content": mod, "citations": []})
    st.markdown("---")
    st.markdown("**History**")
    for a in [x for x in db.approvals() if x["status"] != "pending"][-20:]:
        st.write(f"{a['approval_id']} · {a['level']} · {a['status']} by {a['resolved_by']} · run {a['run_id']}")

with tab_mem:
    rows = db.memories()
    st.subheader(f"{len(rows)} memories")
    st.caption("Importance rises with retrievals and decays over time; near-duplicates are consolidated. Delete honours user data requests.")
    for r in rows:
        with st.expander(f"{r['kind']} · importance {r['importance']:.2f} · accessed {r['access_count']}× · run {r['run_id']} · user {r['user_id']}"):
            st.write(r["text"])
            if st.button("delete", key=f"del{r['memory_id']}"):
                db.delete_memory(memory_id=r["memory_id"]); st.rerun()

with tab_ledger:
    tot = db.ledger_totals()
    st.subheader("Usage ledger")
    st.json({**tot, "allowance_usd": settings.app_allowance_usd, "remaining_usd": round(settings.app_allowance_usd - tot["committed"], 6)})
    st.caption("Each model call reserves an estimated cost before the request and reconciles actual tokens after. With the local model the price is 0, so tokens are the meaningful column.")
