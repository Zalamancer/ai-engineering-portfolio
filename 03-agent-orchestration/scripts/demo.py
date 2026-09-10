"""Showcase scenario (guide Phase 5.1): research + data analysis + written report + external write.
Starts the local test target, submits the request, runs a worker in-process, and stops at each human
approval. With --auto-approve-local it approves ONLY actions whose target is the local test target and
records them as 'demo-script (auto, local test target)' — not as a human decision.
    uv run python scripts/demo.py [--auto-approve-local] [--require-plan-approval]"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentops.config import settings  # noqa: E402
from agentops.db import DB  # noqa: E402
from agentops.worker import build_orchestrator, process_run  # noqa: E402

REQUEST = ("Research how Uvicorn and FastAPI handle proxy headers (X-Forwarded-For / X-Forwarded-Proto) and HTTPS termination, "
           "using the documentation corpus. Then count how many documentation sections mention proxies and how many mention HTTPS "
           "(use the analytics database). Finally write a short report (max 250 words) with citations and POST it as JSON "
           f"to the team webhook at http://127.0.0.1:{settings.test_target_port}/hook.")


def start_target():
    import uvicorn
    from agentops import testtarget
    server = uvicorn.Server(uvicorn.Config(testtarget.app, host="127.0.0.1", port=settings.test_target_port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)
    return testtarget


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto-approve-local", action="store_true")
    ap.add_argument("--require-plan-approval", action="store_true")
    args = ap.parse_args()
    target = start_target()
    db = DB(settings.db_path)
    orch = build_orchestrator(settings, db)
    run_id = db.create_run(REQUEST, {"require_plan_approval": args.require_plan_approval, "user_id": "default"},
                           {k: getattr(settings, k) for k in ("max_steps", "max_llm_calls", "max_tool_calls", "max_tokens_total", "max_wall_seconds", "max_cost_usd")})
    db.event(run_id, "submitted", "demo-script", {"request": REQUEST})
    print("run", run_id)
    t0 = time.time()
    while True:
        run = db.claim_run("demo-worker", settings.lease_seconds)
        if run is None:
            r = db.get_run(run_id)
            if r["status"] == "paused_for_approval":
                pend = db.approvals(run_id, status="pending")
                if not pend:
                    time.sleep(0.5); continue
                a = pend[0]
                print(f"\n⏸  PAUSED — {a['level']}: {a['reason']}\n   proposed: {json.dumps(a['proposed'])[:400]}")
                local = a["level"] == "approve_action" and str(a["proposed"].get("args", {}).get("url", "")).startswith("http://127.0.0.1")
                if args.auto_approve_local and (local or a["level"] in ("approve_plan", "take_over")):
                    by = "demo-script (auto, local test target)" if local else "demo-script (auto)"
                    db.resolve_approval(a["approval_id"], "approved", {"action": "approve", "by": by}, by)
                    db.update_run(run_id, status="resuming")
                    print(f"   → auto-approved by {by}")
                    continue
                print("   → waiting for a human decision via the UI (streamlit run agentops/ui.py) or POST /approvals/{id}")
                time.sleep(3); continue
            if r["status"] in ("completed", "failed", "paused_budget"):
                break
            time.sleep(0.5); continue
        out = process_run(orch, db, run, "demo-worker", settings)
        print(f"worker: {run['run_id']} → {out.get('status')} {out.get('error') or ''}" + ("" if run["run_id"] == run_id else "  (an older run recovered on the way)"))
        if run["run_id"] == run_id and out.get("status") in ("completed", "failed", "paused_budget"):
            break
    r = db.get_run(run_id)
    ev = db.events(run_id)
    print(f"\n=== {r['status']} in {time.time() - t0:.0f}s · {len(ev)} trace events · llm calls {sum(1 for e in ev if e['kind']=='llm_call')} · "
          f"tool calls {sum(1 for e in ev if e['kind']=='tool_call')} · tokens {sum(e['tokens_in'] or 0 for e in ev)}→{sum(e['tokens_out'] or 0 for e in ev)}")
    for t in db.tasks(run_id):
        print(f"  task {t['idx']} {t['specialist']:<9} {t['status']:<8} attempts={t['attempts']} review_rounds={t['review_rounds']} · {t['title']}")
    if r.get("result"):
        print("\n--- REPORT ---\n" + r["result"]["report"][:1500] + f"\n--- citations: {r['result']['citations']}\n--- caveats: {r['result']['caveats']}")
    print(f"test target received {len(target.RECEIVED)} POST(s)")
    print(json.dumps({"run_id": run_id, "status": r["status"], "posts_received": len(target.RECEIVED), "ledger": db.ledger_totals(run_id)}))


if __name__ == "__main__":
    main()
