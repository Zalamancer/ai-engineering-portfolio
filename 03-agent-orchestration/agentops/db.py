"""SQLite persistence for everything that must survive a worker crash: runs, tasks, trace events,
approvals, the usage ledger, memory records and side-effect idempotency keys.
(Guide: PostgreSQL. Adaptation: SQLite in WAL mode locally — same schema, swappable; see README.)"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, created REAL, updated REAL, request TEXT, options TEXT, status TEXT,
  plan TEXT, result TEXT, error TEXT, budget TEXT, usage TEXT, lease_owner TEXT, lease_expires REAL, step_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY, run_id TEXT, idx INTEGER, title TEXT, specialist TEXT, description TEXT, depends_on TEXT,
  inputs TEXT, expected_output TEXT, complexity TEXT, status TEXT, attempts INTEGER DEFAULT 0, review_rounds INTEGER DEFAULT 0,
  output TEXT, review TEXT, error TEXT, updated REAL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, ts REAL, kind TEXT, agent TEXT, payload TEXT,
  latency_ms REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL, status TEXT
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, ts);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, level TEXT, reason TEXT, proposed TEXT, context TEXT,
  status TEXT, decision TEXT, created REAL, resolved REAL, resolved_by TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
  entry_id TEXT PRIMARY KEY, run_id TEXT, ts REAL, kind TEXT, reserved_usd REAL, actual_usd REAL,
  tokens_in INTEGER, tokens_out INTEGER, note TEXT, reconciled INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memory (
  memory_id TEXT PRIMARY KEY, created REAL, kind TEXT, text TEXT, meta TEXT, importance REAL DEFAULT 1.0,
  access_count INTEGER DEFAULT 0, last_access REAL, run_id TEXT, user_id TEXT DEFAULT 'default'
);
CREATE TABLE IF NOT EXISTS side_effects (
  idempotency_key TEXT PRIMARY KEY, run_id TEXT, task_id TEXT, tool TEXT, ts REAL, result TEXT
);
"""


def now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _j(x: Any) -> str | None:
    return None if x is None else json.dumps(x, ensure_ascii=False, default=str)


def _u(s: str | None) -> Any:
    return None if s is None else json.loads(s)


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    # ---- runs --------------------------------------------------------------------------
    def create_run(self, request: str, options: dict, budget: dict) -> str:
        run_id = new_id("run")
        with self.conn() as c:
            c.execute("INSERT INTO runs (run_id, created, updated, request, options, status, budget, usage) VALUES (?,?,?,?,?,?,?,?)",
                      (run_id, now(), now(), request, _j(options), "pending", _j(budget), _j({})))
        return run_id

    def get_run(self, run_id: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._run_row(r) if r else None

    def _run_row(self, r) -> dict:
        d = dict(r)
        for k in ("options", "plan", "result", "budget", "usage"):
            d[k] = _u(d[k])
        return d

    def list_runs(self, limit: int = 50) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM runs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [self._run_row(r) for r in rows]

    def update_run(self, run_id: str, **fields) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            cols.append(f"{k}=?")
            vals.append(_j(v) if k in ("options", "plan", "result", "budget", "usage") else v)
        cols.append("updated=?")
        vals.append(now())
        with self.conn() as c:
            c.execute(f"UPDATE runs SET {', '.join(cols)} WHERE run_id=?", (*vals, run_id))

    def bump_step(self, run_id: str) -> int:
        with self.conn() as c:
            c.execute("UPDATE runs SET step_count = step_count + 1, updated=? WHERE run_id=?", (now(), run_id))
            return int(c.execute("SELECT step_count FROM runs WHERE run_id=?", (run_id,)).fetchone()[0])

    # ---- worker leases (crash recovery) -------------------------------------------------
    def claim_run(self, owner: str, lease_seconds: int) -> dict | None:
        """Atomically claim one run that is runnable: pending, or running with an expired lease
        (its worker died), or resumable after an approval was resolved."""
        t = now()
        with self.conn() as c:
            c.execute("BEGIN IMMEDIATE")
            r = c.execute("""SELECT run_id FROM runs WHERE
                               (status IN ('pending','resuming')) OR
                               (status IN ('planning','running') AND (lease_expires IS NULL OR lease_expires < ?))
                             ORDER BY created LIMIT 1""", (t,)).fetchone()
            if not r:
                c.execute("COMMIT")
                return None
            c.execute("UPDATE runs SET lease_owner=?, lease_expires=?, updated=? WHERE run_id=?", (owner, t + lease_seconds, t, r[0]))
            c.execute("COMMIT")
        return self.get_run(r[0])

    def renew_lease(self, run_id: str, owner: str, lease_seconds: int) -> None:
        with self.conn() as c:
            c.execute("UPDATE runs SET lease_expires=? WHERE run_id=? AND lease_owner=?", (now() + lease_seconds, run_id, owner))

    def release_lease(self, run_id: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE runs SET lease_owner=NULL, lease_expires=NULL WHERE run_id=?", (run_id,))

    # ---- tasks ----------------------------------------------------------------------------
    def replace_tasks(self, run_id: str, tasks: list[dict]) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM tasks WHERE run_id=?", (run_id,))
            for t in tasks:
                c.execute("""INSERT INTO tasks (task_id, run_id, idx, title, specialist, description, depends_on, inputs, expected_output,
                             complexity, status, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (t["task_id"], run_id, t["idx"], t["title"], t["specialist"], t["description"], _j(t.get("depends_on", [])),
                           _j(t.get("inputs", {})), t.get("expected_output", ""), t.get("complexity", "medium"), "pending", now()))

    def tasks(self, run_id: str) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY idx", (run_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("depends_on", "inputs", "output", "review"):
                d[k] = _u(d[k])
            out.append(d)
        return out

    def update_task(self, task_id: str, **fields) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            cols.append(f"{k}=?")
            vals.append(_j(v) if k in ("depends_on", "inputs", "output", "review") else v)
        cols.append("updated=?")
        vals.append(now())
        with self.conn() as c:
            c.execute(f"UPDATE tasks SET {', '.join(cols)} WHERE task_id=?", (*vals, task_id))

    # ---- trace events ------------------------------------------------------------------------
    def event(self, run_id: str, kind: str, agent: str, payload: dict, task_id: str | None = None, latency_ms: float | None = None,
              tokens_in: int | None = None, tokens_out: int | None = None, cost_usd: float | None = None, status: str = "ok") -> str:
        eid = new_id("ev")
        with self.conn() as c:
            c.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (eid, run_id, task_id, now(), kind, agent, _j(payload), latency_ms, tokens_in, tokens_out, cost_usd, status))
        return eid

    def events(self, run_id: str) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM events WHERE run_id=? ORDER BY ts", (run_id,)).fetchall()
        return [{**dict(r), "payload": _u(r["payload"])} for r in rows]

    # ---- approvals ------------------------------------------------------------------------------
    def create_approval(self, run_id: str, task_id: str | None, level: str, reason: str, proposed: dict, context: dict) -> str:
        aid = new_id("apr")
        with self.conn() as c:
            c.execute("INSERT INTO approvals (approval_id, run_id, task_id, level, reason, proposed, context, status, created) VALUES (?,?,?,?,?,?,?,?,?)",
                      (aid, run_id, task_id, level, reason, _j(proposed), _j(context), "pending", now()))
        return aid

    def approvals(self, run_id: str | None = None, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM approvals", []
        conds = []
        if run_id:
            conds.append("run_id=?"); args.append(run_id)
        if status:
            conds.append("status=?"); args.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        with self.conn() as c:
            rows = c.execute(q + " ORDER BY created", args).fetchall()
        return [{**dict(r), "proposed": _u(r["proposed"]), "context": _u(r["context"]), "decision": _u(r["decision"])} for r in rows]

    def get_approval(self, approval_id: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        return {**dict(r), "proposed": _u(r["proposed"]), "context": _u(r["context"]), "decision": _u(r["decision"])} if r else None

    def resolve_approval(self, approval_id: str, status: str, decision: dict, by: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE approvals SET status=?, decision=?, resolved=?, resolved_by=? WHERE approval_id=? AND status='pending'",
                      (status, _j(decision), now(), by, approval_id))

    def resolve_consumed(self, approval_id: str) -> None:
        a = self.get_approval(approval_id)
        if a:
            d = dict(a["decision"] or {}); d["consumed"] = True
            with self.conn() as c:
                c.execute("UPDATE approvals SET decision=? WHERE approval_id=?", (_j(d), approval_id))

    # ---- usage ledger ------------------------------------------------------------------------------
    def reserve(self, run_id: str, kind: str, reserved_usd: float, note: str = "") -> str:
        eid = new_id("led")
        with self.conn() as c:
            c.execute("INSERT INTO ledger (entry_id, run_id, ts, kind, reserved_usd, actual_usd, tokens_in, tokens_out, note, reconciled) VALUES (?,?,?,?,?,?,?,?,?,0)",
                      (eid, run_id, now(), kind, reserved_usd, None, None, None, note))
        return eid

    def reconcile(self, entry_id: str, actual_usd: float, tokens_in: int | None, tokens_out: int | None) -> None:
        with self.conn() as c:
            c.execute("UPDATE ledger SET actual_usd=?, tokens_in=?, tokens_out=?, reconciled=1 WHERE entry_id=?", (actual_usd, tokens_in, tokens_out, entry_id))

    def ledger_totals(self, run_id: str | None = None) -> dict:
        q = "SELECT COALESCE(SUM(CASE WHEN reconciled=1 THEN actual_usd ELSE reserved_usd END),0) AS committed, " \
            "COALESCE(SUM(actual_usd),0) AS actual, COALESCE(SUM(tokens_in),0) AS tokens_in, COALESCE(SUM(tokens_out),0) AS tokens_out, " \
            "COUNT(*) AS entries, SUM(CASE WHEN reconciled=0 THEN 1 ELSE 0 END) AS open_reservations FROM ledger"
        args: list = []
        if run_id:
            q += " WHERE run_id=?"; args.append(run_id)
        with self.conn() as c:
            r = c.execute(q, args).fetchone()
        return dict(r)

    # ---- side-effect idempotency ---------------------------------------------------------------------
    def side_effect_done(self, key: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT result FROM side_effects WHERE idempotency_key=?", (key,)).fetchone()
        return _u(r["result"]) if r else None

    def record_side_effect(self, key: str, run_id: str, task_id: str | None, tool: str, result: dict) -> None:
        with self.conn() as c:
            c.execute("INSERT OR IGNORE INTO side_effects VALUES (?,?,?,?,?,?)", (key, run_id, task_id, tool, now(), _j(result)))

    # ---- memory records (vectors live in Chroma) --------------------------------------------------------
    def add_memory(self, kind: str, text: str, meta: dict, run_id: str | None, importance: float = 1.0, user_id: str = "default") -> str:
        mid = new_id("mem")
        with self.conn() as c:
            c.execute("INSERT INTO memory (memory_id, created, kind, text, meta, importance, access_count, last_access, run_id, user_id) VALUES (?,?,?,?,?,?,0,NULL,?,?)",
                      (mid, now(), kind, text, _j(meta), importance, run_id, user_id))
        return mid

    def touch_memory(self, ids: list[str]) -> None:
        if not ids:
            return
        with self.conn() as c:
            c.executemany("UPDATE memory SET access_count=access_count+1, last_access=?, importance=importance+0.1 WHERE memory_id=?",
                          [(now(), i) for i in ids])

    def memories(self, user_id: str | None = None, limit: int = 200) -> list[dict]:
        with self.conn() as c:
            if user_id:
                rows = c.execute("SELECT * FROM memory WHERE user_id=? ORDER BY importance DESC, created DESC LIMIT ?", (user_id, limit)).fetchall()
            else:
                rows = c.execute("SELECT * FROM memory ORDER BY importance DESC, created DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "meta": _u(r["meta"])} for r in rows]

    def delete_memory(self, memory_id: str | None = None, user_id: str | None = None) -> int:
        with self.conn() as c:
            if memory_id:
                cur = c.execute("DELETE FROM memory WHERE memory_id=?", (memory_id,))
            elif user_id:
                cur = c.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
            else:
                return 0
            return cur.rowcount

    def decay_memories(self, factor: float = 0.98) -> None:
        with self.conn() as c:
            c.execute("UPDATE memory SET importance = importance * ?", (factor,))
