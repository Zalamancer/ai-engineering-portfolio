"""SQLite + JSON storage (guide: 'SQLite + JSON files — zero infrastructure, git-friendly')."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, created TEXT, prompt_version TEXT, prompt_path TEXT, model TEXT, judge_model TEXT,
  dataset_version TEXT, dataset_fingerprint TEXT, n_cases INTEGER, n_verified INTEGER,
  pass_rate REAL, category_accuracy REAL, summary_pass_rate REAL, output_valid_rate REAL,
  latency_p50_ms REAL, latency_p95_ms REAL, prompt_tokens INTEGER, completion_tokens INTEGER,
  baseline_run_id TEXT, status TEXT, notes TEXT, summary_json TEXT
);
CREATE TABLE IF NOT EXISTS case_results (
  run_id TEXT, case_id TEXT, expected_category TEXT, predicted_category TEXT, category_correct INTEGER,
  output_valid INTEGER, validation_error TEXT, summary_score INTEGER, summary_pass INTEGER, passed INTEGER,
  latency_ms REAL, prompt_tokens INTEGER, completion_tokens INTEGER, raw_output TEXT, predicted_summary TEXT, difficulty TEXT,
  confidence REAL, probabilities TEXT,
  PRIMARY KEY (run_id, case_id)
);
"""
# columns added after the first runs were stored; applied to older databases on open
MIGRATIONS = ["ALTER TABLE case_results ADD COLUMN confidence REAL", "ALTER TABLE case_results ADD COLUMN probabilities TEXT"]


class Store:
    def __init__(self, db_path: Path, runs_dir: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                self.db.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        self.runs_dir = runs_dir

    def save_run(self, meta: dict, cases: list[dict]) -> None:
        cols = ("run_id created prompt_version prompt_path model judge_model dataset_version dataset_fingerprint n_cases n_verified "
                "pass_rate category_accuracy summary_pass_rate output_valid_rate latency_p50_ms latency_p95_ms prompt_tokens "
                "completion_tokens baseline_run_id status notes summary_json").split()
        row = {c: meta.get(c) for c in cols}
        row["summary_json"] = json.dumps(meta)
        self.db.execute(f"INSERT OR REPLACE INTO runs ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [row[c] for c in cols])
        ccols = ("run_id case_id expected_category predicted_category category_correct output_valid validation_error summary_score "
                 "summary_pass passed latency_ms prompt_tokens completion_tokens raw_output predicted_summary difficulty confidence probabilities").split()

        def cell(c, k):
            v = c.get(k)
            return json.dumps(v) if k == "probabilities" and v is not None else v
        self.db.executemany(f"INSERT OR REPLACE INTO case_results ({','.join(ccols)}) VALUES ({','.join('?' * len(ccols))})",
                            [[meta["run_id"]] + [cell(c, k) for k in ccols[1:]] for c in cases])
        self.db.commit()
        d = self.runs_dir / meta["run_id"]
        d.mkdir(exist_ok=True)
        (d / "summary.json").write_text(json.dumps(meta, indent=1))
        (d / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False))

    def get_run(self, run_id: str) -> dict | None:
        r = self.db.execute("SELECT summary_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r["summary_json"]) if r else None

    def get_cases(self, run_id: str) -> dict[str, dict]:
        rows = self.db.execute("SELECT * FROM case_results WHERE run_id=?", (run_id,)).fetchall()
        out = {}
        for r in rows:
            d = dict(r)
            if d.get("probabilities"):
                d["probabilities"] = json.loads(d["probabilities"])
            out[d["case_id"]] = d
        return out

    def list_runs(self, limit: int = 50, prompt_version: str | None = None) -> list[dict]:
        q = "SELECT summary_json FROM runs" + (" WHERE prompt_version=?" if prompt_version else "") + " ORDER BY created DESC, rowid DESC LIMIT ?"
        args = ([prompt_version] if prompt_version else []) + [limit]
        return [json.loads(r["summary_json"]) for r in self.db.execute(q, args).fetchall()]

    def latest_baseline(self, backend: str = "openai") -> dict | None:
        """Newest baseline for this backend — a jev candidate is diffed against a jev baseline, never an LLM one."""
        for r in self.db.execute("SELECT summary_json FROM runs WHERE status='baseline' ORDER BY created DESC, rowid DESC").fetchall():
            meta = json.loads(r["summary_json"])
            if meta.get("backend", "openai") == backend:
                return meta
        return None

    def mark_baseline(self, run_id: str) -> None:
        meta = self.get_run(run_id)
        if not meta:
            raise KeyError(run_id)
        meta["status"] = "baseline"
        self.db.execute("UPDATE runs SET status='baseline', summary_json=? WHERE run_id=?", (json.dumps(meta), run_id))
        self.db.commit()
        (self.runs_dir / run_id / "summary.json").write_text(json.dumps(meta, indent=1))


def new_run_id(prompt_version: str) -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}_{prompt_version}"
