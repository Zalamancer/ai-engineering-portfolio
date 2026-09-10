"""Orchestration API (guide Phase 5): submit runs, watch progress, resolve approvals, inspect traces,
memory dashboard + delete, usage ledger. Workers (agentops.worker) do the actual execution."""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .config import settings
from .db import DB

app = FastAPI(title="agentops — supervisor / specialists / reviewer with human-in-the-loop", version=__version__)
db = DB(settings.db_path)


class RunRequest(BaseModel):
    request: str = Field(min_length=10, max_length=4000)
    require_plan_approval: bool = False
    user_id: str = "default"


class Decision(BaseModel):
    action: Literal["approve", "reject", "modify", "take_over"]
    plan: dict | None = None            # for modify on approve_plan
    args: dict | None = None            # for modify on approve_action
    content: str | None = None          # for take_over
    citations: list[str] | None = None
    by: str = "human"


@app.get("/health")
def health():
    return {"status": "ok", "db": str(settings.db_path), "budgets": {k: getattr(settings, k) for k in
            ("max_steps", "max_llm_calls", "max_tool_calls", "max_tokens_total", "max_wall_seconds", "max_retries_per_task", "max_review_rounds", "max_cost_usd", "app_allowance_usd")},
            "ledger": db.ledger_totals()}


@app.post("/runs", status_code=201)
def create_run(req: RunRequest):
    budget = {k: getattr(settings, k) for k in ("max_steps", "max_llm_calls", "max_tool_calls", "max_tokens_total", "max_wall_seconds", "max_cost_usd")}
    run_id = db.create_run(req.request, {"require_plan_approval": req.require_plan_approval, "user_id": req.user_id}, budget)
    db.event(run_id, "submitted", "api", {"request": req.request})
    return {"run_id": run_id, "status": "pending"}


@app.get("/runs")
def list_runs(limit: int = 50):
    return [{k: r[k] for k in ("run_id", "created", "updated", "status", "request", "error")} for r in db.list_runs(limit)]


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    r.pop("lease_owner", None)
    return {**r, "tasks": db.tasks(run_id), "approvals": db.approvals(run_id), "ledger": db.ledger_totals(run_id)}


@app.get("/runs/{run_id}/trace")
def trace(run_id: str, kinds: str | None = None):
    if not db.get_run(run_id):
        raise HTTPException(404, "unknown run")
    ev = db.events(run_id)
    if kinds:
        ks = set(kinds.split(","))
        ev = [e for e in ev if e["kind"] in ks]
    totals = {"events": len(ev), "llm_calls": sum(1 for e in ev if e["kind"] == "llm_call"),
              "tool_calls": sum(1 for e in ev if e["kind"] == "tool_call"),
              "tokens_in": sum(e["tokens_in"] or 0 for e in ev), "tokens_out": sum(e["tokens_out"] or 0 for e in ev),
              "cost_usd": round(sum(e["cost_usd"] or 0 for e in ev), 6),
              "wall_seconds": round(ev[-1]["ts"] - ev[0]["ts"], 1) if ev else 0}
    return {"run_id": run_id, "totals": totals, "events": ev}


@app.post("/runs/{run_id}/cancel")
def cancel(run_id: str):
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    if r["status"] in ("completed", "failed"):
        return {"status": r["status"]}
    db.update_run(run_id, status="failed", error="cancelled by user")
    db.event(run_id, "cancelled", "human", {})
    return {"status": "failed", "error": "cancelled by user"}


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str, by: str = "human"):
    """Human decision to continue a run that stopped on a budget (after raising the limits via env)."""
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "unknown run")
    if r["status"] != "paused_budget":
        raise HTTPException(409, f"run is {r['status']}, only paused_budget runs can be resumed here")
    db.update_run(run_id, status="resuming", error=None)
    db.event(run_id, "budget_extended", by, {"previous_error": r["error"], "budgets": {k: getattr(settings, k) for k in ("max_steps", "max_llm_calls", "max_tool_calls", "max_wall_seconds")}})
    return {"run_id": run_id, "status": "resuming"}


@app.get("/approvals")
def pending_approvals(status: str = "pending"):
    return db.approvals(status=status)


@app.post("/approvals/{approval_id}")
def decide(approval_id: str, d: Decision):
    a = db.get_approval(approval_id)
    if not a:
        raise HTTPException(404, "unknown approval")
    if a["status"] != "pending":
        raise HTTPException(409, f"already {a['status']}")
    status = {"approve": "approved", "reject": "rejected", "modify": "modified", "take_over": "taken_over"}[d.action]
    db.resolve_approval(approval_id, status, d.model_dump(exclude_none=True), d.by)
    db.update_run(a["run_id"], status="resuming")
    return {"approval_id": approval_id, "status": status, "run_status": "resuming"}


@app.get("/memory")
def memory_dashboard(user_id: str | None = None):
    rows = db.memories(user_id=user_id)
    return {"count": len(rows), "memories": rows}


@app.delete("/memory/{memory_id}")
def delete_memory(memory_id: str):
    from .worker import build_orchestrator  # lazy: loads the embedding model
    orch = build_orchestrator(settings, db)
    n = orch.memory.delete(memory_id=memory_id) if orch.memory else db.delete_memory(memory_id=memory_id)
    return {"deleted": n}


@app.delete("/memory")
def delete_user_memory(user_id: str):
    """User data deletion request: removes all memories for a user from SQLite and Chroma."""
    from .worker import build_orchestrator
    orch = build_orchestrator(settings, db)
    n = orch.memory.delete(user_id=user_id) if orch.memory else db.delete_memory(user_id=user_id)
    return {"deleted": n, "user_id": user_id}


@app.get("/ledger")
def ledger(run_id: str | None = None):
    return {"totals": db.ledger_totals(run_id), "allowance_usd": settings.app_allowance_usd,
            "remaining_usd": round(settings.app_allowance_usd - db.ledger_totals()["committed"], 6),
            "note": "reservations are made before each model call and reconciled after; local model price is 0 so USD stays 0 while tokens are tracked"}
