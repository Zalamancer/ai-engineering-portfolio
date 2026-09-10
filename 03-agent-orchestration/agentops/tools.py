"""Tool registry (guide Phase 1.3): each tool has a name, description, Pydantic input/output schemas,
the specialists allowed to use it, a per-run rate limit and a side-effect flag. Every invocation is
validated, logged (inputs, outputs, latency, success/failure) and counted against the budget.
Side-effecting tools are idempotent per (run, task, args) so a restarted worker never repeats them."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import Settings


class ToolError(Exception):
    pass


class ToolDenied(ToolError):
    pass


class RateLimited(ToolError):
    pass


# ---------------------------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------------------------
class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(5, ge=1, le=10)


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str


class SearchOut(BaseModel):
    source: str
    results: list[SearchHit]


class FetchIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    max_chars: int = Field(6000, ge=200, le=20000)


class FetchOut(BaseModel):
    url: str
    status: int
    text: str
    truncated: bool


class FileReadIn(BaseModel):
    path: str = Field(min_length=1, max_length=200)


class FileReadOut(BaseModel):
    path: str
    text: str


class FileWriteIn(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=200_000)


class FileWriteOut(BaseModel):
    path: str
    bytes: int


class PyIn(BaseModel):
    code: str = Field(min_length=1, max_length=20_000)


class PyOut(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


class SqlIn(BaseModel):
    sql: str = Field(min_length=6, max_length=4000)


class SqlOut(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


class PostIn(BaseModel):
    url: str
    json_body: dict


class PostOut(BaseModel):
    status: int
    response_text: str
    idempotent_replay: bool = False


class MemIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    k: int = Field(5, ge=1, le=10)


class MemOut(BaseModel):
    memories: list[dict]


# ---------------------------------------------------------------------------------------------
@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    allowed_specialists: tuple[str, ...]
    fn: Callable[..., BaseModel]
    rate_limit_per_run: int = 20
    side_effect: bool = False
    sensitive: bool = False

    def schema_for_prompt(self) -> dict:
        return {"name": self.name, "description": self.description, "args": self.input_model.model_json_schema().get("properties", {})}


@dataclass
class ToolContext:
    run_id: str
    task_id: str | None
    specialist: str
    workspace: Path
    db: Any = None
    memory: Any = None
    counts: dict = field(default_factory=dict)


class ToolRegistry:
    def __init__(self, settings: Settings):
        self.s = settings
        self.tools: dict[str, Tool] = {}
        self.total_calls: dict[str, int] = {}
        self._register_defaults()

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def for_specialist(self, specialist: str) -> list[Tool]:
        return [t for t in self.tools.values() if specialist in t.allowed_specialists]

    def describe(self, specialist: str) -> list[dict]:
        return [t.schema_for_prompt() for t in self.for_specialist(specialist)]

    # ---- the single choke point every invocation goes through -----------------------------
    def invoke(self, name: str, args: dict, ctx: ToolContext, max_tool_calls: int) -> dict:
        t0 = time.perf_counter()
        tool = self.tools.get(name)
        log = ctx.db.event if ctx.db else (lambda *a, **k: None)
        try:
            if tool is None:
                raise ToolError(f"unknown tool {name!r}")
            if ctx.specialist not in tool.allowed_specialists:
                raise ToolDenied(f"{ctx.specialist} may not use {name}")
            n_run = self.total_calls.get(ctx.run_id, 0)
            if n_run >= max_tool_calls:
                raise RateLimited(f"run tool-call budget {max_tool_calls} exhausted")
            n_tool = ctx.counts.get(name, 0)
            if n_tool >= tool.rate_limit_per_run:
                raise RateLimited(f"{name} rate limit {tool.rate_limit_per_run}/run exceeded")
            try:
                inp = tool.input_model(**args)
            except ValidationError as e:
                raise ToolError(f"invalid arguments for {name}: {e.errors()[0]['msg']} at {e.errors()[0]['loc']}")
            self.total_calls[ctx.run_id] = n_run + 1
            ctx.counts[name] = n_tool + 1
            # idempotency for side effects: same (run, task, tool, args) → replay stored result
            key = None
            if tool.side_effect and ctx.db:
                key = hashlib.sha256(f"{ctx.run_id}|{ctx.task_id}|{name}|{json.dumps(args, sort_keys=True)}".encode()).hexdigest()
                prior = ctx.db.side_effect_done(key)
                if prior is not None:
                    prior = {**prior, "idempotent_replay": True}
                    log(ctx.run_id, "tool_call", ctx.specialist, {"tool": name, "args": args, "result": prior, "replayed": True},
                        task_id=ctx.task_id, latency_ms=0.0, status="replayed")
                    return prior
            out = tool.fn(inp, ctx, self.s)
            out = tool.output_model.model_validate(out if isinstance(out, dict) else out.model_dump())
            result = out.model_dump()
            if key:
                ctx.db.record_side_effect(key, ctx.run_id, ctx.task_id, name, result)
            log(ctx.run_id, "tool_call", ctx.specialist, {"tool": name, "args": args, "result": _clip(result)},
                task_id=ctx.task_id, latency_ms=round((time.perf_counter() - t0) * 1000, 1), status="ok")
            return result
        except ToolError as e:
            log(ctx.run_id, "tool_call", ctx.specialist, {"tool": name, "args": args, "error": str(e)},
                task_id=ctx.task_id, latency_ms=round((time.perf_counter() - t0) * 1000, 1), status="error")
            raise
        except Exception as e:
            log(ctx.run_id, "tool_call", ctx.specialist, {"tool": name, "args": args, "error": f"{type(e).__name__}: {e}"},
                task_id=ctx.task_id, latency_ms=round((time.perf_counter() - t0) * 1000, 1), status="error")
            raise ToolError(f"{name} failed: {type(e).__name__}: {e}") from e

    # ---- default tools -------------------------------------------------------------------------
    def _register_defaults(self) -> None:
        self.register(Tool("docs_search", "Search the team's documentation corpus (FastAPI/Starlette/Uvicorn docs + HTTP RFCs). Returns titled passages with source URLs to cite.",
                           SearchIn, SearchOut, ("research",), docs_search, rate_limit_per_run=10))
        self.register(Tool("web_search", "Web search (DuckDuckGo). Offline fixture unless AO_WEB_SEARCH_LIVE=true.",
                           SearchIn, SearchOut, ("research",), web_search, rate_limit_per_run=6))
        self.register(Tool("fetch_url", "Fetch a web page as text (https only, size-capped).", FetchIn, FetchOut, ("research",), fetch_url, rate_limit_per_run=6))
        self.register(Tool("read_file", "Read a file from the run workspace.", FileReadIn, FileReadOut, ("research", "analysis", "writing"), read_file))
        self.register(Tool("write_file", "Write a file into the run workspace (sensitive: needs approval).", FileWriteIn, FileWriteOut,
                           ("analysis", "writing"), write_file, side_effect=True, sensitive=True))
        self.register(Tool("python_exec", "Run a short Python snippet in an isolated subprocess (no network, time/memory limited) and return stdout.",
                           PyIn, PyOut, ("analysis",), python_exec, rate_limit_per_run=8))
        self.register(Tool("sql_query", "Read-only SQL (SQLite dialect, SELECT only) over the demo analytics database. " + _sql_schema_text(self.s),
                           SqlIn, SqlOut, ("analysis",), sql_query, rate_limit_per_run=10))
        self.register(Tool("http_post", "POST JSON to an external endpoint (allow-listed local test target only; sensitive: needs approval).",
                           PostIn, PostOut, ("writing",), http_post, rate_limit_per_run=3, side_effect=True, sensitive=True))
        self.register(Tool("memory_search", "Search long-term memory of past runs and facts.", MemIn, MemOut, ("research", "analysis", "writing"), memory_search))


def _clip(x: Any, n: int = 4000) -> Any:
    s = json.dumps(x, default=str)
    return x if len(s) <= n else {"_clipped": s[:n] + "…"}


# ---------------------------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------------------------
_DOCS_INDEX: dict | None = None


def _load_docs_index(path: Path):
    """Tiny BM25 over the project-1 corpus so research is deterministic and offline."""
    global _DOCS_INDEX
    if _DOCS_INDEX is not None:
        return _DOCS_INDEX
    from rank_bm25 import BM25Okapi  # vendored through chromadb deps? no — fall back to simple scoring
    docs = []
    if path.exists():
        with path.open() as fh:
            for line in fh:
                d = json.loads(line)
                # split into heading sections for finer results
                for sec in re.split(r"\n(?=#{1,6} )", d["text"]):
                    if len(sec.strip()) > 80:
                        docs.append({"doc_id": d["doc_id"], "title": d.get("title", ""), "url": d.get("source_url", ""), "text": sec.strip()[:3000]})
    tok = lambda s: re.findall(r"[a-z0-9_]+(?:[-.][a-z0-9_]+)*", s.lower())
    _DOCS_INDEX = {"docs": docs, "bm25": BM25Okapi([tok(d["text"]) for d in docs]) if docs else None, "tok": tok}
    return _DOCS_INDEX


def docs_search(inp: SearchIn, ctx: ToolContext, s: Settings) -> SearchOut:
    idx = _load_docs_index(s.docs_corpus_path)
    if not idx["bm25"]:
        raise ToolError("documentation corpus not available (run project 1 ingest first)")
    import numpy as np
    scores = idx["bm25"].get_scores(idx["tok"](inp.query))
    top = np.argsort(-scores)[: inp.max_results]
    hits = []
    for i in top:
        if scores[i] <= 0:
            continue
        d = idx["docs"][i]
        heading = d["text"].split("\n", 1)[0].lstrip("# ")[:100]
        hits.append(SearchHit(title=f"{d['title']} — {heading}", url=d["url"], snippet=d["text"][:700]))
    return SearchOut(source="docs_corpus", results=hits)


_FIXTURE = [SearchHit(title="Uvicorn settings", url="https://www.uvicorn.org/settings/", snippet="--proxy-headers / --no-proxy-headers: Enable/Disable X-Forwarded-Proto, X-Forwarded-For to populate remote address info."),
            SearchHit(title="FastAPI — Behind a Proxy", url="https://fastapi.tiangolo.com/advanced/behind-a-proxy/", snippet="root_path is a mechanism provided by the ASGI specification to handle a proxy with a stripped path prefix.")]


def web_search(inp: SearchIn, ctx: ToolContext, s: Settings) -> SearchOut:
    if not s.web_search_live:
        return SearchOut(source="fixture (AO_WEB_SEARCH_LIVE=false)", results=_FIXTURE[: inp.max_results])
    from ddgs import DDGS
    res = DDGS().text(inp.query, max_results=inp.max_results) or []
    return SearchOut(source="duckduckgo", results=[SearchHit(title=r.get("title", ""), url=r.get("href", ""), snippet=r.get("body", "")) for r in res])


def fetch_url(inp: FetchIn, ctx: ToolContext, s: Settings) -> FetchOut:
    if not inp.url.startswith(tuple(s.fetch_allowlist)):
        raise ToolDenied(f"url scheme/host not allowed: {inp.url[:60]}")
    r = httpx.get(inp.url, timeout=15, follow_redirects=True, headers={"User-Agent": "agentops-portfolio/0.1"})
    text = r.text
    if "html" in r.headers.get("content-type", ""):
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
    return FetchOut(url=str(r.url), status=r.status_code, text=text[: inp.max_chars], truncated=len(text) > inp.max_chars)


def _safe_path(ws: Path, rel: str) -> Path:
    p = (ws / rel).resolve()
    if not str(p).startswith(str(ws.resolve())):
        raise ToolDenied("path escapes the run workspace")
    return p


def read_file(inp: FileReadIn, ctx: ToolContext, s: Settings) -> FileReadOut:
    p = _safe_path(ctx.workspace, inp.path)
    if not p.exists():
        raise ToolError(f"no such file in workspace: {inp.path}")
    return FileReadOut(path=inp.path, text=p.read_text()[:50_000])


def write_file(inp: FileWriteIn, ctx: ToolContext, s: Settings) -> FileWriteOut:
    p = _safe_path(ctx.workspace, inp.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(inp.text)
    return FileWriteOut(path=inp.path, bytes=len(inp.text.encode()))


def python_exec(inp: PyIn, ctx: ToolContext, s: Settings) -> PyOut:
    """Isolated subprocess: fresh temp cwd, isolated mode (-I), empty environment, CPU/memory/file
    limits via resource, and a wall-clock timeout. Network is blocked by disallowing the socket
    module at import time (best effort — this is a lightweight sandbox, not a VM; see README)."""
    banned = ("import socket", "import subprocess", "import os", "from os", "import shutil", "import sys", "import http", "import urllib", "import requests", "import httpx", "open(")
    if any(b in inp.code for b in banned):
        raise ToolDenied("code uses a module/function outside the sandbox allow-list (os, sys, socket, subprocess, network, file open)")
    prelude = ("import builtins,sys\n"
               "_blocked={'socket','subprocess','os','shutil','http','urllib','requests','httpx','ctypes','importlib','pathlib'}\n"
               "_imp=builtins.__import__\n"
               "def _guard(name,*a,**k):\n"
               "    if name.split('.')[0] in _blocked: raise ImportError(f'{name} is blocked in the sandbox')\n"
               "    return _imp(name,*a,**k)\n"
               "builtins.__import__=_guard\n"
               "builtins.open=None\n")
    with tempfile.TemporaryDirectory() as td:
        code_path = Path(td) / "snippet.py"
        code_path.write_text(prelude + inp.code)

        def limits():
            import resource
            mem = s.python_exec_mem_mb * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except (ValueError, OSError):
                pass
            resource.setrlimit(resource.RLIMIT_CPU, (s.python_exec_timeout_s, s.python_exec_timeout_s))
            resource.setrlimit(resource.RLIMIT_FSIZE, (1_000_000, 1_000_000))
            resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
        try:
            p = subprocess.run([sys.executable, "-I", "-S", str(code_path)], cwd=td, env={}, capture_output=True, text=True,
                               timeout=s.python_exec_timeout_s, preexec_fn=limits)
            return PyOut(stdout=p.stdout[-8000:], stderr=p.stderr[-2000:], exit_code=p.returncode, timed_out=False)
        except subprocess.TimeoutExpired as e:
            return PyOut(stdout=(e.stdout or "")[-8000:] if isinstance(e.stdout, str) else "", stderr="timed out", exit_code=-1, timed_out=True)


def _sql_schema_text(s: Settings) -> str:
    """Column list for the prompt, so specialists do not have to guess column names."""
    import sqlite3
    db_path = s.data_dir / "demo_analytics.sqlite"
    if not db_path.exists():
        return "Schema: (database not seeded — run scripts/seed_demo_db.py)."
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        parts = []
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({name})")]
            parts.append(f"{name}({', '.join(cols)})")
        return "Schema: " + "; ".join(parts) + ". Note: sections has no text column — only headings and mention flags (0/1)."
    finally:
        c.close()


_SQL_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|pragma|replace|vacuum)\b", re.I)


def sql_query(inp: SqlIn, ctx: ToolContext, s: Settings) -> SqlOut:
    import sqlite3
    if _SQL_FORBIDDEN.search(inp.sql) or not inp.sql.strip().lower().startswith(("select", "with")):
        raise ToolDenied("only read-only SELECT queries are allowed")
    db_path = s.data_dir / "demo_analytics.sqlite"
    if not db_path.exists():
        raise ToolError("demo analytics database missing — run scripts/seed_demo_db.py")
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c.execute("PRAGMA query_only=1")
    try:
        cur = c.execute(inp.sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(201)
    except sqlite3.OperationalError as e:
        raise ToolError(f"SQL error: {e}. {_sql_schema_text(s)}")
    finally:
        c.close()
    return SqlOut(columns=cols, rows=[list(r) for r in rows[:200]], row_count=min(len(rows), 200), truncated=len(rows) > 200)


def http_post(inp: PostIn, ctx: ToolContext, s: Settings) -> PostOut:
    if not inp.url.startswith(tuple(s.http_post_allowlist)):
        raise ToolDenied(f"external writes are only allowed to the local test target {s.http_post_allowlist}")
    r = httpx.post(inp.url, json=inp.json_body, timeout=10)
    return PostOut(status=r.status_code, response_text=r.text[:500])


def memory_search(inp: MemIn, ctx: ToolContext, s: Settings) -> MemOut:
    if ctx.memory is None:
        return MemOut(memories=[])
    return MemOut(memories=ctx.memory.search(inp.query, k=inp.k))
