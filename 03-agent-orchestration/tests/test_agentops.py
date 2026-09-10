"""End-to-end tests with a scripted FakeLLM: these verify the orchestration plumbing (plans, tools,
review loop, approvals, budgets, crash recovery). They say nothing about model quality."""
from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from agentops import agents
from agentops.config import Settings
from agentops.db import DB
from agentops.graph import Orchestrator
from agentops.llm import BudgetExhausted, FakeLLM
from agentops.memory import Memory, hash_embedder
from agentops.tools import ToolContext, ToolDenied, ToolError, ToolRegistry
from agentops.worker import process_run

PLAN = json.dumps({"confidence": 0.9, "rationale": "two steps", "tasks": [
    {"idx": 1, "title": "Find proxy header docs", "specialist": "research", "description": "Search the docs corpus for how Uvicorn handles X-Forwarded headers and report with sources.", "depends_on": [], "inputs": [], "expected_output": "facts with citations", "complexity": "low"},
    {"idx": 2, "title": "Write summary and post", "specialist": "writing", "description": "Write a 3-sentence summary from task 1 and POST it to the team webhook.", "depends_on": [1], "inputs": ["task 1 output"], "expected_output": "markdown", "complexity": "low"}]})
LOW_CONF_PLAN = PLAN.replace('"confidence": 0.9', '"confidence": 0.3')
RESEARCH_SEARCH = json.dumps({"thought": "search", "action": {"tool": "docs_search", "args": {"query": "uvicorn proxy headers X-Forwarded-For", "max_results": 3}}})
ACCEPT = json.dumps({"verdict": "accept", "score": 5, "feedback": "good", "issues": []})
REJECT = json.dumps({"verdict": "reject", "score": 2, "feedback": "you did not mention X-Forwarded-Proto", "issues": ["incomplete"]})


def research_final(url):
    return json.dumps({"thought": "done", "final": {"summary": "Uvicorn trusts X-Forwarded-* only from allowed IPs.", "content": "Uvicorn's --proxy-headers reads X-Forwarded-Proto and X-Forwarded-For; --forwarded-allow-ips controls trust.", "citations": [url]}})


def writing_post(port):
    return json.dumps({"thought": "post", "action": {"tool": "http_post", "args": {"url": f"http://127.0.0.1:{port}/hook", "json_body": {"report": "Uvicorn proxy headers summary"}}}})


def writing_final(url):  # cites the research task's source: inherited evidence must be accepted by the reviewer
    return json.dumps({"thought": "done", "final": {"summary": "posted", "content": "# Report\nUvicorn trusts forwarded headers from allowed IPs.", "citations": [url]}})


@pytest.fixture
def env(tmp_path):
    s = Settings(data_dir=tmp_path, db_path=tmp_path / "a.db", checkpoint_db_path=tmp_path / "c.db", chroma_dir=tmp_path / "chroma",
                 workspace_dir=tmp_path / "ws", http_post_allowlist=("http://127.0.0.1:8098",), plan_confidence_threshold=0.6)
    db = DB(s.db_path)
    return s, db


def _first_url(db, run_id):
    for e in db.events(run_id):
        if e["kind"] == "tool_call" and e["payload"].get("tool") == "docs_search":
            return e["payload"]["result"]["results"][0]["url"]
    return "https://www.uvicorn.org/settings/"


class ScriptedLLM(FakeLLM):
    """Role-aware script: the same object serves supervisor/specialist/reviewer prompts."""
    def __init__(self, s, db, run_id, plan=PLAN, reviews=None, research_turns=None, writing_turns=None, port=8098):
        super().__init__(settings=s, db=db, run_id=run_id)
        self.plan = plan
        self.reviews = list(reviews or [ACCEPT, ACCEPT])
        self.research_turns = research_turns
        self.writing_turns = writing_turns
        self.port = port
        self.db_ = db

    def chat(self, messages, max_tokens=700, temperature=0.0, agent="llm", task_id=None):
        text = messages[-1]["content"]
        if text.startswith("You are the SUPERVISOR of"):
            reply = self.plan
        elif text.startswith("You are the REVIEWER"):
            reply = self.reviews.pop(0) if self.reviews else ACCEPT
        elif text.startswith("You are the research specialist"):
            if self.research_turns:
                reply = self.research_turns.pop(0)
            elif "YOU CALLED docs_search" in text:
                reply = research_final(_first_url(self.db_, self.run_id))
            else:
                reply = RESEARCH_SEARCH
        elif text.startswith("You are the writing specialist"):
            if self.writing_turns:
                reply = self.writing_turns.pop(0)
            elif "YOU CALLED http_post" in text:
                reply = writing_final(_first_url(self.db_, self.run_id))
            else:
                reply = writing_post(self.port)
        else:
            reply = json.dumps({"report": "r", "citations": [], "caveats": []})
        self.rules = [(text[:40], reply)]
        return super().chat(messages, max_tokens, temperature, agent, task_id)


def make_orch(s, db, llm, memory=None):
    return Orchestrator(s, db, lambda run_id, role: llm, ToolRegistry(s), memory, checkpoint_path=s.checkpoint_db_path)


# ---------------------------------------------------------------------------------------------
def test_plan_contract_rejects_bad_dags():
    with pytest.raises(Exception):
        agents.parse_plan(json.dumps({"confidence": 0.8, "tasks": [{"idx": 1, "title": "a task", "specialist": "research", "description": "x" * 20, "depends_on": [2]}]}))
    with pytest.raises(Exception):
        agents.parse_plan(json.dumps({"confidence": 0.8, "tasks": [{"idx": 1, "title": "a task", "specialist": "wizard", "description": "x" * 20}]}))
    p = agents.parse_plan("```json\n" + PLAN + "\n```")
    assert [t.idx for t in p.tasks] == [1, 2] and p.tasks[1].depends_on == [1]


def test_extract_json_tolerates_trailing_brace_and_prose():
    from agentops.llm import extract_json
    assert extract_json('{"a": {"b": 1}}}') == {"a": {"b": 1}}
    assert extract_json('Sure! ```json\n{"final": {"x": 2}}\n``` hope this helps') == {"final": {"x": 2}}


def test_tool_registry_validates_permissions_args_and_limits(env, tmp_path):
    s, db = env
    reg = ToolRegistry(s)
    ws = tmp_path / "ws"
    ws.mkdir()
    ctx = ToolContext("run_x", "t1", "research", ws, db=db)
    with pytest.raises(ToolDenied):        # research may not run python
        reg.invoke("python_exec", {"code": "print(1)"}, ctx, 10)
    with pytest.raises(ToolError):         # bad args
        reg.invoke("docs_search", {"query": "x"}, ctx, 10)
    with pytest.raises(ToolError):         # unknown tool
        reg.invoke("rm_rf", {}, ctx, 10)
    actx = ToolContext("run_x", "t2", "analysis", ws, db=db)
    out = reg.invoke("python_exec", {"code": "print(sum(range(10)))"}, actx, 10)
    assert out["stdout"].strip() == "45" and out["exit_code"] == 0
    with pytest.raises(ToolDenied):        # sandbox blocks os / network imports
        reg.invoke("python_exec", {"code": "import os\nprint(os.listdir('/'))"}, actx, 10)
    with pytest.raises(ToolDenied):        # read-only SQL
        reg.invoke("sql_query", {"sql": "DELETE FROM docs"}, actx, 10)
    with pytest.raises(ToolDenied):        # workspace escape
        reg.invoke("read_file", {"path": "../../etc/passwd"}, actx, 10)
    with pytest.raises(ToolDenied):        # external write outside allow-list
        reg.invoke("http_post", {"url": "https://hooks.slack.com/x", "json_body": {}}, ToolContext("run_x", "t3", "writing", ws, db=db), 10)
    with pytest.raises(ToolError):         # run-wide tool budget
        reg.invoke("python_exec", {"code": "print(1)"}, actx, max_tool_calls=1)
    kinds = [e["status"] for e in db.events("run_x") if e["kind"] == "tool_call"]
    assert "ok" in kinds and "error" in kinds  # every invocation, good or bad, is logged


@pytest.fixture
def target():
    """Real local HTTP test target on :8098 (the only allow-listed external write destination)."""
    import uvicorn
    from agentops import testtarget
    testtarget.RECEIVED.clear()
    cfg = uvicorn.Config(testtarget.app, host="127.0.0.1", port=8098, log_level="error")
    server = uvicorn.Server(cfg)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    import time
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)
    yield testtarget
    server.should_exit = True
    th.join(timeout=3)


def test_happy_path_with_bounded_review_correction_and_sensitive_approval(env, target):
    s, db = env
    run_id = db.create_run("Summarise how Uvicorn handles proxy headers and post it to the team webhook", {}, {})
    llm = ScriptedLLM(s, db, run_id, reviews=[REJECT, ACCEPT, ACCEPT])   # reviewer rejects research once
    mem = Memory(s, db, embed=hash_embedder())
    orch = make_orch(s, db, llm, mem)
    out = orch.start(db.get_run(run_id))
    # writing wants http_post (sensitive) → paused for approval
    assert out["status"] == "paused_for_approval" and out["interrupt"]["level"] == "approve_action"
    pend = db.approvals(run_id, status="pending")
    assert len(pend) == 1 and pend[0]["proposed"]["tool"] == "http_post"
    assert target.RECEIVED == []                                          # nothing posted before approval
    db.resolve_approval(pend[0]["approval_id"], "approved", {"action": "approve"}, "test-human")
    out = orch.resume(run_id, {"action": "approve"})
    assert out["status"] == "completed", out
    assert len(target.RECEIVED) == 1                                      # exactly one external write
    assert len(db.approvals(run_id)) == 1                                 # approved action executed as-is, never re-asked
    assert target.RECEIVED[0]["body"] == pend[0]["proposed"]["args"]["json_body"]  # exactly what the human saw
    run = db.get_run(run_id)
    tasks = db.tasks(run_id)
    assert [t["status"] for t in tasks] == ["done", "done"]
    assert tasks[0]["review_rounds"] == 1                                 # one bounded correction round
    assert tasks[1]["review_rounds"] == 0                                 # inherited citation accepted, no false rejection
    assert run["result"]["citations"] and all(c.startswith("http") for c in run["result"]["citations"])
    kinds = [e["kind"] for e in db.events(run_id)]
    for k in ("memory_retrieval", "plan", "tool_call", "review", "approval_requested", "approval_resolved", "synthesis", "delivered"):
        assert k in kinds
    assert any(e["kind"] == "review" and e["status"] == "warning" for e in db.events(run_id))
    assert mem.dashboard()["count"] >= 1                                  # episode stored in long-term memory
    assert mem.search("proxy headers uvicorn")[0]["run_id"] == run_id


def test_low_confidence_plan_pauses_and_human_can_modify(env):
    s, db = env
    run_id = db.create_run("Do research on Uvicorn proxy headers only", {}, {})
    llm = ScriptedLLM(s, db, run_id, plan=LOW_CONF_PLAN)
    orch = make_orch(s, db, llm)
    out = orch.start(db.get_run(run_id))
    assert out["status"] == "paused_for_approval" and out["interrupt"]["level"] == "approve_plan"
    assert db.get_run(run_id)["status"] == "paused_for_approval"
    new_plan = json.loads(PLAN)
    new_plan["tasks"] = new_plan["tasks"][:1]                              # human drops the posting step
    out = orch.resume(run_id, {"action": "modify", "plan": new_plan})
    assert out["status"] == "completed"
    assert len(db.tasks(run_id)) == 1 and db.tasks(run_id)[0]["status"] == "done"
    assert any(e["kind"] == "plan" and e["agent"] == "human" for e in db.events(run_id))


def test_budget_exhaustion_produces_explicit_paused_state(env):
    s, db = env
    s = s.model_copy(update={"max_llm_calls": 2})
    run_id = db.create_run("Summarise how Uvicorn handles proxy headers", {}, {})
    llm = ScriptedLLM(s, db, run_id)
    orch = make_orch(s, db, llm)
    out = orch.start(db.get_run(run_id))
    assert out["status"] == "paused_budget" and "max_llm_calls" in out["error"]
    assert db.get_run(run_id)["status"] == "paused_budget"
    assert any(e["kind"] == "budget" for e in db.events(run_id))


def test_unavailable_tool_leads_to_explicit_failure_after_bounded_retries(env):
    s, db = env
    s = s.model_copy(update={"max_retries_per_task": 1, "max_tool_iterations_per_task": 2})
    run_id = db.create_run("Summarise how Uvicorn handles proxy headers", {}, {})
    bad = json.dumps({"thought": "x", "action": {"tool": "teleport", "args": {}}})
    llm = ScriptedLLM(s, db, run_id, plan=json.dumps({**json.loads(PLAN), "tasks": json.loads(PLAN)["tasks"][:1]}), research_turns=[bad] * 10)
    orch = make_orch(s, db, llm)
    out = orch.start(db.get_run(run_id))
    t = db.tasks(run_id)[0]
    assert t["status"] == "failed" and t["attempts"] == 2
    assert out["status"] in ("completed", "failed") and db.get_run(run_id)["result"]["caveats"]
    assert any(e["kind"] == "retry" for e in db.events(run_id))


def test_killed_worker_resumes_without_repeating_side_effects(env, target):
    s, db = env
    run_id = db.create_run("Summarise how Uvicorn handles proxy headers and post it", {}, {})
    llm = ScriptedLLM(s, db, run_id)
    reg = ToolRegistry(s)
    crashed = {"done": False}
    real_post = reg.tools["http_post"].fn

    def crashing_post(inp, ctx, st):
        out = real_post(inp, ctx, st)              # the external write happens ...
        if not crashed["done"]:
            crashed["done"] = True
            db.record_side_effect(__import__("hashlib").sha256(f"{ctx.run_id}|{ctx.task_id}|http_post|{json.dumps({'url': inp.url, 'json_body': inp.json_body}, sort_keys=True)}".encode()).hexdigest(),
                                  ctx.run_id, ctx.task_id, "http_post", out.model_dump())
            raise KeyboardInterrupt("simulated worker kill right after the write")   # ... then the process dies
        return out
    reg.tools["http_post"].fn = crashing_post
    orch = Orchestrator(s, db, lambda r, role: llm, reg, None, checkpoint_path=s.checkpoint_db_path)
    out = orch.start(db.get_run(run_id))
    assert out["status"] == "paused_for_approval"
    pend = db.approvals(run_id, status="pending")[0]
    db.resolve_approval(pend["approval_id"], "approved", {"action": "approve"}, "h")
    with pytest.raises(KeyboardInterrupt):
        orch.resume(run_id, {"action": "approve"})
    assert len(target.RECEIVED) == 1
    # a fresh worker (new orchestrator object, same checkpoint db) recovers from the last checkpoint
    orch2 = Orchestrator(s, db, lambda r, role: llm, ToolRegistry(s), None, checkpoint_path=s.checkpoint_db_path)
    db.update_run(run_id, status="running", lease_expires=0)
    out = process_run(orch2, db, db.get_run(run_id), "worker-2", s)
    assert out["status"] == "completed", out
    assert len(target.RECEIVED) == 1                                       # not repeated
    ev = db.events(run_id)
    assert any(e["kind"] == "tool_call" and e["status"] == "replayed" for e in ev)
    assert any(e["kind"] == "worker" and e["payload"].get("action") == "recover_from_checkpoint" for e in ev)


def test_api_surfaces_runs_approvals_trace_and_ledger(env, monkeypatch):
    s, db = env
    from agentops import api
    monkeypatch.setattr(api, "db", db)
    client = TestClient(api.app)
    r = client.post("/runs", json={"request": "Research Uvicorn proxy headers and write a summary", "require_plan_approval": True})
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    assert db.get_run(run_id)["status"] == "pending"
    assert client.get(f"/runs/{run_id}").json()["options"]["require_plan_approval"] is True
    assert client.get(f"/runs/{run_id}/trace").json()["totals"]["events"] == 1
    assert client.get("/health").json()["budgets"]["max_steps"] == s.max_steps
    assert client.get("/ledger").json()["remaining_usd"] == s.app_allowance_usd
    aid = db.create_approval(run_id, None, "approve_plan", "user requested", {"plan": {}}, {"key": "plan"})
    assert client.post(f"/approvals/{aid}", json={"action": "approve"}).json()["run_status"] == "resuming"
    assert client.post(f"/approvals/{aid}", json={"action": "approve"}).status_code == 409


def test_reviewer_rejects_numbers_not_backed_by_tool_results(env):
    s, db = env
    run_id = db.create_run("Count sections and report", {}, {})
    plan = json.dumps({"confidence": 0.9, "tasks": [{"idx": 1, "title": "Count proxy sections", "specialist": "analysis",
                       "description": "Count how many sections mention proxies using the analytics database.", "depends_on": [], "expected_output": "a number"}]})
    sql = json.dumps({"thought": "q", "action": {"tool": "sql_query", "args": {"sql": "SELECT SUM(mentions_proxy) FROM sections"}}})
    bad_final = json.dumps({"thought": "d", "final": {"summary": "There are 12 proxy sections.", "content": "12 sections mention proxies.", "citations": ["sql://SELECT SUM(mentions_proxy) FROM sections"]}})
    llm = ScriptedLLM(s, db, run_id, plan=plan, research_turns=None)
    # analysis script: first SQL call, then a final that invents a number; second attempt returns the real number
    real = {"n": None}
    class L(ScriptedLLM):
        def chat(self, messages, **kw):
            text = messages[-1]["content"]
            if text.startswith("You are the analysis specialist"):
                if "YOU CALLED sql_query" not in text:
                    return FakeLLM.chat(self, messages, agent="analysis", **{k: v for k, v in kw.items() if k != "agent"}) if False else self._reply(messages, sql)
                if real["n"] is None:
                    import re
                    m = re.search(r"\[\[(\d+)\]\]", text)
                    real["n"] = m.group(1) if m else "0"
                    return self._reply(messages, bad_final)
                return self._reply(messages, json.dumps({"thought": "d", "final": {"summary": f"There are {real['n']} proxy sections.", "content": f"{real['n']} sections mention proxies.", "citations": ["sql://SELECT SUM(mentions_proxy) FROM sections"]}}))
            return super().chat(messages, **kw)
        def _reply(self, messages, reply):
            self.rules = [(messages[-1]["content"][:40], reply)]
            return FakeLLM.chat(self, messages)
    llm = L(s, db, run_id, plan=plan)
    import shutil
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "data" / "demo_analytics.sqlite"
    if not src.exists():
        pytest.skip("demo analytics db not seeded")
    shutil.copy(src, s.data_dir / "demo_analytics.sqlite")
    out = make_orch(s, db, llm).start(db.get_run(run_id))
    assert out["status"] == "completed"
    t = db.tasks(run_id)[0]
    assert t["review_rounds"] == 1 and t["status"] == "done"
    reviews = [e["payload"] for e in db.events(run_id) if e["kind"] == "review"]
    assert reviews[0]["verdict"] == "reject" and "ungrounded_numbers" in reviews[0]["issues"]
    assert reviews[-1]["verdict"] == "accept" and real["n"] in t["output"]["content"]


def test_memory_consolidation_and_delete(env):
    s, db = env
    m = Memory(s, db, embed=hash_embedder())
    a = m.store("fact", "uvicorn trusts forwarded headers from allowed ips", {}, run_id="r1", user_id="u1")
    b = m.store("fact", "uvicorn trusts forwarded headers from allowed ips", {}, run_id="r2", user_id="u1")
    m.store("fact", "cookies with HttpOnly are hidden from scripts", {}, run_id="r3", user_id="u2")
    merged = m.consolidate(threshold=0.95)
    assert len(merged) == 1 and m.dashboard()["count"] == 2
    assert m.delete(user_id="u1") == 1 and m.dashboard()["count"] == 1 and m.search("cookies")[0]["run_id"] == "r3"
