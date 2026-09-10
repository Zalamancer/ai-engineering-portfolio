"""Worker process: claims runnable runs with a lease, drives the graph, and can be killed at any
time — a restarted worker picks the run up from the last LangGraph checkpoint (expired lease), and
tool side effects are idempotent, so nothing external is repeated.

    uv run python -m agentops.worker            # loop
    uv run python -m agentops.worker --once     # process at most one run then exit
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time

from .config import Settings, settings as default_settings
from .db import DB
from .graph import Orchestrator
from .llm import LLM
from .memory import Memory
from .tools import ToolRegistry


def build_orchestrator(s: Settings, db: DB, llm_factory=None, memory: Memory | None | bool = True) -> Orchestrator:
    if llm_factory is None:
        def llm_factory(run_id, role):
            return LLM(s, db, run_id, model=(s.reviewer_model or None) if role == "reviewer" else None)
    if memory is True:
        try:
            memory = Memory(s, db)
        except Exception as e:  # embedding model missing etc. — memory is optional
            print(f"memory disabled: {e}", file=sys.stderr)
            memory = None
    return Orchestrator(s, db, llm_factory, ToolRegistry(s), memory or None)


def process_run(orch: Orchestrator, db: DB, run: dict, owner: str, s: Settings) -> dict:
    run_id = run["run_id"]
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(s.lease_seconds / 3):
            db.renew_lease(run_id, owner, s.lease_seconds)
    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()
    try:
        if run["status"] == "pending":
            db.event(run_id, "worker", owner, {"action": "start"})
            out = orch.start(run)
        elif run["status"] == "resuming":
            decision = None
            for a in db.approvals(run_id):
                if a["status"] in ("approved", "rejected", "modified", "taken_over") and not (a["decision"] or {}).get("consumed"):
                    decision = dict(a["decision"] or {})
                    db.resolve_consumed(a["approval_id"])
                    break
            if decision is None:
                # resumed by a human after a budget pause (no interrupt pending) → continue from the last checkpoint
                db.event(run_id, "worker", owner, {"action": "resume_after_budget_pause"})
                out = orch.resume(run_id, None)
            else:
                db.event(run_id, "worker", owner, {"action": "resume_after_approval", "decision": decision})
                out = orch.resume(run_id, decision)
        else:  # planning/running with an expired lease → the previous worker died
            db.event(run_id, "worker", owner, {"action": "recover_from_checkpoint", "previous_owner": run.get("lease_owner")}, status="warning")
            out = orch.resume(run_id, None)
        return out
    except Exception as e:
        db.update_run(run_id, status="failed", error=f"{type(e).__name__}: {e}")
        db.event(run_id, "error", owner, {"error": f"{type(e).__name__}: {e}"}, status="error")
        return {"status": "failed", "error": str(e)}
    finally:
        stop.set()
        db.release_lease(run_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--owner", default=f"worker-{os.getpid()}")
    args = ap.parse_args()
    s = default_settings
    db = DB(s.db_path)
    orch = build_orchestrator(s, db)
    print(f"{args.owner} polling {s.db_path}")
    while True:
        run = db.claim_run(args.owner, s.lease_seconds)
        if run:
            print(f"{args.owner} → {run['run_id']} ({run['status']})", flush=True)
            out = process_run(orch, db, run, args.owner, s)
            print(f"{args.owner} ← {run['run_id']} {out.get('status')}", flush=True)
            if args.once:
                return
        elif args.once:
            print("nothing to do")
            return
        else:
            time.sleep(s.worker_poll_s)


if __name__ == "__main__":
    main()
