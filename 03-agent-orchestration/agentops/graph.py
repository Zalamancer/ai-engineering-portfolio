"""LangGraph state machine (guide Phase 1.4):
intake → plan → [approve_plan?] → execute (parallel ready tasks) → review → (back to execute | synthesize) → deliver.
Human approvals use LangGraph interrupt(); all state is checkpointed to SQLite after every node,
so a killed worker resumes from the last checkpoint, and side effects inside tools are idempotent."""
from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from . import agents
from .config import Settings
from .db import DB, now
from .llm import BudgetExhausted, extract_json
from .tools import ToolContext, ToolError, ToolRegistry


class RunState(TypedDict, total=False):
    run_id: str
    request: str
    options: dict
    started: float
    memories: list[dict]
    plan: dict
    tasks: list[dict]                 # [{task_id, idx, title, specialist, ..., status, output, review_rounds, attempts, feedback}]
    transcripts: dict                 # task_id -> list of steps (for replay after interrupt/crash)
    active_s: float                   # seconds spent inside nodes (wall-clock budget basis)
    evidence: dict                    # task_id -> list of urls/doc ids seen in tool results
    approved_actions: list[str]       # keys of sensitive actions a human approved
    to_review: list[str]
    result: dict
    status: str
    error: str
    step: int


class Orchestrator:
    """Builds the graph with its runtime dependencies (db, llm factory, tools, memory) bound in."""

    def __init__(self, settings: Settings, db: DB, llm_factory, registry: ToolRegistry, memory=None, checkpoint_path: Path | None = None):
        self.s = settings
        self.db = db
        self.llm_factory = llm_factory          # (run_id, role) -> LLM-like
        self.registry = registry
        self.memory = memory
        cp = checkpoint_path or settings.checkpoint_db_path
        cp.parent.mkdir(parents=True, exist_ok=True)
        self.saver = SqliteSaver(sqlite3.connect(str(cp), check_same_thread=False))
        self.graph = self._build()

    # ------------------------------------------------------------------ helpers -----------------
    def _llm(self, run_id: str, role: str):
        return self.llm_factory(run_id, role)

    def _check_budget(self, state: RunState, node: str) -> None:
        """Steps and ACTIVE wall-clock (time spent inside nodes, persisted in state) — so a run that sat
        idle while its worker was dead or while a human was deciding is not charged for that time."""
        step = self.db.bump_step(state["run_id"])
        if step > self.s.max_steps:
            raise BudgetExhausted(f"max_steps={self.s.max_steps} reached at node {node}")
        active = float(state.get("active_s") or 0.0)
        if active > self.s.max_wall_seconds:
            raise BudgetExhausted(f"max_wall_seconds={self.s.max_wall_seconds} of active processing exceeded at node {node} (active {active:.0f}s)")
        self.db.event(state["run_id"], "state", "graph", {"node": node, "step": step, "active_s": round(active, 1)})

    def _timed(self, fn):
        """Wrap a node so its execution time is added to state['active_s']."""
        def wrapper(state: RunState) -> dict:
            t0 = time.time()
            try:
                out = fn(state) or {}
            finally:
                pass
            out["active_s"] = float(state.get("active_s") or 0.0) + (time.time() - t0)
            return out
        wrapper.__name__ = fn.__name__
        return wrapper

    def _approval(self, state: RunState, task_id: str | None, level: str, reason: str, proposed: dict, key: str) -> dict:
        """Create (once) a pending approval and pause. Re-entry after resume returns the human decision."""
        run_id = state["run_id"]
        existing = [a for a in self.db.approvals(run_id) if (a["context"] or {}).get("key") == key]
        if not any(a["status"] == "pending" for a in existing):
            if not existing:
                self.db.create_approval(run_id, task_id, level, reason, proposed,
                                        {"key": key, "request": state["request"], "plan": state.get("plan"),
                                         "completed": [t["title"] for t in state.get("tasks", []) if t["status"] == "done"],
                                         "memories": state.get("memories", [])[:3]})
                self.db.event(run_id, "approval_requested", "supervisor", {"level": level, "reason": reason, "proposed": proposed}, task_id=task_id, status="paused")
        self.db.update_run(run_id, status="paused_for_approval")
        decision = interrupt({"level": level, "reason": reason, "proposed": proposed, "key": key})
        self.db.event(run_id, "approval_resolved", "human", {"level": level, "decision": decision}, task_id=task_id)
        self.db.update_run(run_id, status="running")
        return decision or {}

    # ------------------------------------------------------------------ nodes -------------------
    def intake(self, state: RunState) -> dict:
        self._check_budget(state, "intake")
        run_id = state["run_id"]
        self.db.update_run(run_id, status="planning")
        mems = []
        if self.memory is not None:
            try:
                mems = self.memory.search(state["request"], k=4)
            except Exception as e:  # memory must never break a run
                self.db.event(run_id, "error", "memory", {"error": str(e)}, status="error")
        self.db.event(run_id, "memory_retrieval", "supervisor", {"query": state["request"], "hits": mems})
        return {"memories": mems, "started": state.get("started") or time.time(), "transcripts": {}, "evidence": {}, "approved_actions": [], "status": "planning"}

    def plan(self, state: RunState) -> dict:
        self._check_budget(state, "plan")
        run_id = state["run_id"]
        if state.get("plan"):  # re-entry after an approval interrupt: do not re-plan
            plan = state["plan"]
        else:
            llm = self._llm(run_id, "supervisor")
            mem_block = ""
            if state.get("memories"):
                mem_block = "\nRELEVANT MEMORY FROM PAST RUNS (may inform the plan):\n" + "\n".join(f"- {m['text'][:300]}" for m in state["memories"]) + "\n"
            prompt = agents.SUPERVISOR_PROMPT.format(request=state["request"], memory_block=mem_block)
            plan = None
            errors = []
            for attempt in range(2):
                res = llm.chat([{"role": "user", "content": prompt if not errors else prompt + f"\n\nYour previous reply was invalid: {errors[-1]}. Reply with valid JSON only."}],
                               max_tokens=900, agent="supervisor")
                try:
                    plan = agents.parse_plan(res.text).model_dump()
                    break
                except Exception as e:
                    errors.append(str(e)[:300])
                    self.db.event(run_id, "retry", "supervisor", {"reason": "invalid plan", "error": str(e)[:300], "attempt": attempt + 1}, status="warning")
            if plan is None:
                raise RuntimeError(f"supervisor could not produce a valid plan: {errors}")
            self.db.event(run_id, "plan", "supervisor", plan)
        tasks = state.get("tasks") or [
            {"task_id": f"{run_id}_t{t['idx']}", "run_id": run_id, **t, "status": "pending", "attempts": 0, "review_rounds": 0, "feedback": "", "output": None}
            for t in plan["tasks"]]
        self.db.replace_tasks(run_id, tasks)
        self.db.update_run(run_id, plan=plan)

        needs_human = plan["confidence"] < self.s.plan_confidence_threshold or self.s.always_approve_plan or (state.get("options") or {}).get("require_plan_approval")
        if needs_human:
            reason = ("user requested plan review" if (state.get("options") or {}).get("require_plan_approval") or self.s.always_approve_plan
                      else f"supervisor confidence {plan['confidence']:.2f} < {self.s.plan_confidence_threshold}")
            decision = self._approval(state, None, "approve_plan", reason, {"plan": plan}, key="plan")
            action = decision.get("action", "approve")
            if action == "reject":
                self.db.update_run(run_id, status="failed", error="plan rejected by human")
                return {"plan": plan, "tasks": tasks, "status": "failed", "error": "plan rejected by human"}
            if action == "modify" and decision.get("plan"):
                plan = agents.Plan(**decision["plan"]).model_dump()
                tasks = [{"task_id": f"{run_id}_t{t['idx']}", "run_id": run_id, **t, "status": "pending", "attempts": 0, "review_rounds": 0, "feedback": "", "output": None} for t in plan["tasks"]]
                self.db.replace_tasks(run_id, tasks)
                self.db.update_run(run_id, plan=plan)
                self.db.event(run_id, "plan", "human", {"modified_plan": plan})
        self.db.update_run(run_id, status="running")
        return {"plan": plan, "tasks": tasks, "status": "running"}

    def _ready(self, tasks: list[dict]) -> list[dict]:
        done = {t["idx"] for t in tasks if t["status"] == "done"}
        return [t for t in tasks if t["status"] in ("pending", "rejected") and all(d in done for d in t["depends_on"])]

    def execute(self, state: RunState) -> dict:
        self._check_budget(state, "execute")
        run_id = state["run_id"]
        tasks = [dict(t) for t in state["tasks"]]
        transcripts = dict(state.get("transcripts", {}))
        evidence = dict(state.get("evidence", {}))
        approved = list(state.get("approved_actions", []))
        ready = self._ready(tasks)[: self.s.max_concurrency]
        if not ready:
            return {"to_review": []}
        by_id = {t["task_id"]: t for t in tasks}
        outputs = {t["idx"]: t["output"] for t in tasks if t["status"] == "done"}

        def run_one(task: dict) -> dict:
            return self._run_specialist(state, task, outputs, transcripts.get(task["task_id"], []), approved)

        if len(ready) == 1:
            results = [run_one(ready[0])]
        else:
            with ThreadPoolExecutor(max_workers=len(ready)) as ex:
                results = list(ex.map(run_one, ready))

        pending_sensitive = None
        for task, r in zip(ready, results):
            transcripts[task["task_id"]] = r["transcript"]
            evidence[task["task_id"]] = r["evidence"]
            t = by_id[task["task_id"]]
            if r["kind"] == "needs_approval":
                pending_sensitive = (t, r)
                t["status"] = "pending"
            elif r["kind"] == "final":
                t.update(status="review", output=r["output"], attempts=t["attempts"] + 1)
                self.db.update_task(t["task_id"], status="review", output=r["output"], attempts=t["attempts"])
            else:  # failed
                t["attempts"] += 1
                if t["attempts"] > self.s.max_retries_per_task:
                    t.update(status="failed", error=r["error"])
                    self.db.update_task(t["task_id"], status="failed", error=r["error"], attempts=t["attempts"])
                    self.db.event(run_id, "error", t["specialist"], {"task": t["title"], "error": r["error"], "attempts": t["attempts"]}, task_id=t["task_id"], status="error")
                else:
                    t.update(status="pending", feedback=f"Previous attempt failed: {r['error']}. Try a different approach.")
                    self.db.update_task(t["task_id"], status="pending", attempts=t["attempts"], error=r["error"])
                    self.db.event(run_id, "retry", t["specialist"], {"task": t["title"], "error": r["error"], "attempt": t["attempts"]}, task_id=t["task_id"], status="warning")
                    transcripts[t["task_id"]] = []  # start over with a fresh approach

        update = {"tasks": tasks, "transcripts": transcripts, "evidence": evidence, "approved_actions": approved,
                  "to_review": [t["task_id"] for t in tasks if t["status"] == "review"]}
        if pending_sensitive:
            t, r = pending_sensitive
            key = r["action_key"]
            decision = self._approval(state, t["task_id"], "approve_action", f"{t['specialist']} wants to call sensitive tool {r['tool']}",
                                      {"tool": r["tool"], "args": r["args"], "task": t["title"], "thought": r.get("thought", "")}, key=key)
            act = decision.get("action", "approve")
            if act == "approve":
                approved.append(key)
                transcripts[t["task_id"]].append({"kind": "human_modify", "tool": r["tool"], "args": r["args"], "approved_as_is": True})
            elif act == "modify":
                approved.append(key)
                transcripts[t["task_id"]].append({"kind": "human_modify", "tool": r["tool"], "args": decision.get("args", r["args"])})
            elif act == "take_over":
                t.update(status="review", output={"summary": "provided by human", "content": decision.get("content", ""), "citations": decision.get("citations", []), "human": True})
                self.db.update_task(t["task_id"], status="review", output=t["output"])
                update["to_review"] = update["to_review"] + [t["task_id"]]
            else:  # reject the action → specialist continues without it
                transcripts[t["task_id"]].append({"kind": "tool_denied", "tool": r["tool"], "args": r["args"], "error": "human rejected this action; do not attempt it again"})
            update["approved_actions"] = approved
            update["transcripts"] = transcripts
        return update

    def _run_specialist(self, state: RunState, task: dict, outputs: dict, transcript: list[dict], approved: list[str]) -> dict:
        """Bounded tool loop. `transcript` replays earlier steps (after an interrupt or crash) without new LLM calls."""
        run_id = state["run_id"]
        llm = self._llm(run_id, task["specialist"])
        ws = self.s.workspace_dir / run_id
        ws.mkdir(parents=True, exist_ok=True)
        ctx = ToolContext(run_id=run_id, task_id=task["task_id"], specialist=task["specialist"], workspace=ws, db=self.db, memory=self.memory)
        tools = self.registry.describe(task["specialist"])
        inputs_block = ""
        deps = [outputs.get(d) for d in task["depends_on"] if outputs.get(d)]
        if deps:
            inputs_block = "\nOUTPUTS FROM EARLIER TASKS:\n" + "\n---\n".join(agents.clip(d, 2500) for d in deps) + "\n"
        feedback_block = f"\nREVIEWER FEEDBACK ON YOUR PREVIOUS ATTEMPT (fix this): {task['feedback']}\n" if task.get("feedback") else ""
        evidence: list[str] = []
        transcript = list(transcript)
        self.db.update_task(task["task_id"], status="running")
        self.db.event(run_id, "task_start", task["specialist"], {"task": task["title"], "replayed_steps": len(transcript)}, task_id=task["task_id"])

        def history_text():
            parts = []
            for st in transcript:
                if st["kind"] == "tool_result":
                    parts.append(f"\nYOU CALLED {st['tool']}({json.dumps(st['args'])}) → {agents.clip(st['result'], 1800)}")
                elif st["kind"] == "tool_denied":
                    parts.append(f"\nYOU CALLED {st['tool']} → ERROR: {st['error']}")
                elif st["kind"] == "human_modify":
                    parts.append(f"\nA HUMAN APPROVED {st['tool']} with modified args {json.dumps(st['args'])}; call it now with exactly these args.")
            return "\nPREVIOUS TURNS:" + "".join(parts) if parts else ""

        def harvest(result: Any):
            s = json.dumps(result, default=str)
            for url in set(__import__("re").findall(r"https?://[^\s\"'<>\]]+", s)):
                evidence.append(url.rstrip(".,)"))
            if isinstance(result, dict):
                for hit in result.get("results", []) if isinstance(result.get("results"), list) else []:
                    if isinstance(hit, dict) and hit.get("url"):
                        evidence.append(hit["url"])

        for st in transcript:
            if st["kind"] == "tool_result":
                harvest(st["result"])

        for turn in range(len([s for s in transcript if s["kind"] in ("tool_result", "tool_denied")]), self.s.max_tool_iterations_per_task + 1):
            # a human approved/modified an action that has not been executed yet → run exactly that, no new model call
            pending_human = None
            for i_h, st_h in enumerate(transcript):
                if st_h["kind"] == "human_modify" and not any(x["kind"] in ("tool_result", "tool_denied") and x["tool"] == st_h["tool"] for x in transcript[i_h + 1:]):
                    pending_human = st_h
            if pending_human is not None:
                try:
                    result = self.registry.invoke(pending_human["tool"], pending_human["args"], ctx, self.s.max_tool_calls)
                    harvest(result)
                    transcript.append({"kind": "tool_result", "tool": pending_human["tool"], "args": pending_human["args"], "result": result})
                except ToolError as e:
                    transcript.append({"kind": "tool_denied", "tool": pending_human["tool"], "args": pending_human["args"], "error": str(e)[:400]})
                continue
            prompt = agents.SPECIALIST_PROMPT.format(specialist=task["specialist"], title=task["title"], description=task["description"],
                                                     expected_output=task.get("expected_output") or "free text", inputs_block=inputs_block,
                                                     feedback_block=feedback_block, tools=json.dumps(tools, ensure_ascii=False),
                                                     turn=turn, max_turns=self.s.max_tool_iterations_per_task, history=history_text())
            try:
                res = llm.chat([{"role": "user", "content": prompt}], max_tokens=1200, agent=task["specialist"], task_id=task["task_id"])
                step = agents.parse_specialist(res.text)
            except BudgetExhausted:
                raise
            except Exception as e:
                transcript.append({"kind": "tool_denied", "tool": "(reply)", "args": {}, "error": f"your reply was not valid JSON with action/final: {str(e)[:200]}"})
                continue
            if step["kind"] == "final":
                self.db.event(run_id, "task_final", task["specialist"], {"output": step["output"], "thought": step["thought"]}, task_id=task["task_id"])
                return {"kind": "final", "output": step["output"], "transcript": transcript, "evidence": sorted(set(evidence))}
            tool = self.registry.tools.get(step["tool"])
            action_key = f"{task['task_id']}|{step['tool']}|{json.dumps(step['args'], sort_keys=True)}"
            if tool is not None and tool.sensitive and action_key not in approved:
                modified = [s for s in transcript if s["kind"] == "human_modify" and s["tool"] == step["tool"]]
                if not modified:
                    return {"kind": "needs_approval", "tool": step["tool"], "args": step["args"], "thought": step["thought"],
                            "action_key": action_key, "transcript": transcript, "evidence": sorted(set(evidence))}
            try:
                args = step["args"]
                mod = [s for s in transcript if s["kind"] == "human_modify" and s["tool"] == step["tool"]]
                if mod:
                    args = mod[-1]["args"]
                result = self.registry.invoke(step["tool"], args, ctx, self.s.max_tool_calls)
                harvest(result)
                transcript.append({"kind": "tool_result", "tool": step["tool"], "args": args, "result": result})
            except ToolError as e:
                transcript.append({"kind": "tool_denied", "tool": step["tool"], "args": step["args"], "error": str(e)[:400]})
        return {"kind": "failed", "error": f"specialist exhausted {self.s.max_tool_iterations_per_task} tool turns without a final result",
                "transcript": transcript, "evidence": sorted(set(evidence))}

    def review(self, state: RunState) -> dict:
        self._check_budget(state, "review")
        run_id = state["run_id"]
        tasks = [dict(t) for t in state["tasks"]]
        by_id = {t["task_id"]: t for t in tasks}
        llm = self._llm(run_id, "reviewer")
        transcripts = dict(state.get("transcripts", {}))
        for tid in state.get("to_review", []):
            t = by_id[tid]
            if t["status"] != "review":
                continue
            output = t["output"] or {}
            ev = set(state.get("evidence", {}).get(tid, []))
            # sources handed down from completed dependency tasks are legitimate evidence too
            for dep in tasks:
                if dep["idx"] in t["depends_on"] and dep["status"] == "done":
                    ev.update((dep.get("output") or {}).get("citations", []))
                    ev.update(state.get("evidence", {}).get(dep["task_id"], []))
            # programmatic check first: every citation must be something the specialist actually retrieved
            used_tools = {st.get("tool") for st in state.get("transcripts", {}).get(tid, []) if st.get("kind") == "tool_result"}
            def _supported(c: str) -> bool:
                if c in ev or any(c in e or e in c for e in ev):
                    return True
                # non-URL provenance ("sql://SELECT …", "python_exec", "tool:sql_query") is fine if that tool was actually called
                if not c.startswith("http"):
                    return any(tool and (tool in c or c.split(":")[0] in tool) for tool in used_tools) or (t["specialist"] != "research" and bool(used_tools))
                return False
            unsupported = [c for c in output.get("citations", []) if not _supported(c)]
            required_post = bool(__import__("re").search(r"\b(post|webhook|send)\b", t["description"] + " " + t["title"], __import__("re").I)) and t["specialist"] == "writing"
            posted = any(st.get("kind") == "tool_result" and st.get("tool") == "http_post" for st in state.get("transcripts", {}).get(tid, []))
            # numeric grounding: any multi-digit number in the output must appear in a tool result or a dependency output
            import re as _re
            numbers = set(_re.findall(r"(?<![\w.])\d{2,}(?![\w])", (output.get("content") or "") + " " + (output.get("summary") or "")))
            grounded_text = " ".join(json.dumps(st.get("result", ""), default=str) for st in state.get("transcripts", {}).get(tid, []) if st.get("kind") == "tool_result")
            grounded_text += " ".join(json.dumps(d.get("output") or {}, default=str) for d in tasks if d["idx"] in t["depends_on"])
            ungrounded = sorted(n for n in numbers if n not in grounded_text)
            if output.get("human"):
                verdict = {"verdict": "accept", "score": 5, "feedback": "provided by human", "issues": []}
            elif ungrounded and t["specialist"] in ("analysis", "writing"):
                verdict = {"verdict": "reject", "score": 2, "feedback": f"These numbers do not appear in any tool result or earlier task output: {ungrounded[:5]}. Only report figures you actually computed or received.", "issues": ["ungrounded_numbers"]}
            elif required_post and not posted:
                verdict = {"verdict": "reject", "score": 2, "feedback": "The task requires posting the result to the webhook, but no http_post call was made. Call http_post with the report as JSON, then return final.", "issues": ["required_action_not_performed"]}
            elif unsupported and not (t["specialist"] == "writing" and not ev):
                verdict = {"verdict": "reject", "score": 2, "feedback": f"citations not backed by retrieved evidence: {unsupported[:3]}. Cite only sources you retrieved with a tool.", "issues": ["unsupported_citations"]}
            else:
                evidence_text = "\n".join(f"- {e}" for e in sorted(ev)[:20]) or "(none — task did not retrieve external evidence)"
                prompt = agents.REVIEWER_PROMPT.format(specialist=t["specialist"], title=t["title"], description=t["description"],
                                                       expected_output=t.get("expected_output") or "free text", output=agents.clip(output, 4000), evidence=evidence_text)
                try:
                    res = llm.chat([{"role": "user", "content": prompt}], max_tokens=400, agent="reviewer", task_id=tid)
                    verdict = agents.parse_review(res.text).model_dump()
                except BudgetExhausted:
                    raise
                except Exception as e:
                    verdict = {"verdict": "accept", "score": 3, "feedback": f"reviewer output unparseable ({str(e)[:100]}); accepted by default", "issues": ["reviewer_parse_error"]}
            self.db.event(run_id, "review", "reviewer", {"task": t["title"], **verdict}, task_id=tid, status="ok" if verdict["verdict"] == "accept" else "warning")
            if verdict["verdict"] == "accept":
                t.update(status="done", review=verdict)
                self.db.update_task(tid, status="done", review=verdict)
            else:
                t["review_rounds"] += 1
                if t["review_rounds"] <= self.s.max_review_rounds:
                    t.update(status="rejected", feedback=verdict["feedback"], review=verdict)
                    transcripts[tid] = []  # bounded correction: redo with feedback
                    self.db.update_task(tid, status="rejected", review=verdict, review_rounds=t["review_rounds"])
                else:
                    # escalate: reviewer still unhappy after the allowed rounds → human takes over or accepts
                    decision = self._approval(state, tid, "take_over", f"reviewer rejected '{t['title']}' {t['review_rounds']} times (score {verdict['score']})",
                                              {"last_output": output, "review": verdict}, key=f"takeover|{tid}")
                    if decision.get("action") == "take_over":
                        t.update(status="done", output={"summary": "provided by human", "content": decision.get("content", ""), "citations": decision.get("citations", []), "human": True}, review={"verdict": "accept", "score": 5, "feedback": "human take-over"})
                    elif decision.get("action") == "reject":
                        t.update(status="failed", error="rejected by reviewer and human")
                    else:
                        t.update(status="done", review={**verdict, "verdict": "accept", "feedback": "accepted by human despite reviewer"})
                    self.db.update_task(tid, status=t["status"], output=t["output"], review=t["review"])
        return {"tasks": tasks, "transcripts": transcripts, "to_review": []}

    def synthesize(self, state: RunState) -> dict:
        self._check_budget(state, "synthesize")
        run_id = state["run_id"]
        tasks = state["tasks"]
        done = [t for t in tasks if t["status"] == "done"]
        failed = [t for t in tasks if t["status"] == "failed"]
        citations = sorted({c for t in done for c in (t["output"] or {}).get("citations", [])})
        writing = [t for t in done if t["specialist"] == "writing"]
        if writing and not failed:
            report = writing[-1]["output"].get("content", "")
            caveats = []
        else:
            llm = self._llm(run_id, "supervisor")
            outputs = "\n\n".join(f"### Task {t['idx']}: {t['title']} ({t['specialist']}, {t['status']})\n{agents.clip(t.get('output') or t.get('error'), 3000)}" for t in tasks)
            try:
                res = llm.chat([{"role": "user", "content": agents.SYNTHESIS_PROMPT.format(request=state["request"], outputs=outputs)}], max_tokens=1500, agent="supervisor")
                obj = extract_json(res.text)
                report, caveats = str(obj.get("report", "")), [str(c) for c in obj.get("caveats", [])]
            except BudgetExhausted:
                raise
            except Exception as e:
                report = "\n\n".join(f"## {t['title']}\n{(t.get('output') or {}).get('content', '')}" for t in done)
                caveats = [f"synthesis fell back to concatenation ({str(e)[:80]})"]
        if failed:
            caveats.append(f"{len(failed)} task(s) failed: " + "; ".join(f"{t['title']}: {t.get('error')}" for t in failed))
        result = {"report": report, "citations": citations, "caveats": caveats,
                  "tasks": [{"idx": t["idx"], "title": t["title"], "specialist": t["specialist"], "status": t["status"],
                             "summary": (t.get("output") or {}).get("summary"), "review": t.get("review")} for t in tasks]}
        status = "completed" if not failed or done else "failed"
        self.db.event(run_id, "synthesis", "supervisor", {"citations": citations, "caveats": caveats, "status": status})
        if self.memory is not None:
            try:
                self.memory.store("episode", f"Request: {state['request'][:300]}\nPlan: " + "; ".join(f"{t['idx']}.{t['title']} ({t['specialist']})" for t in tasks)
                                  + f"\nOutcome: {status}; " + (f"caveats: {caveats[:2]}" if caveats else "no caveats"),
                                  {"status": status, "n_tasks": len(tasks)}, run_id=run_id)
                for t in done:
                    if t["specialist"] == "research" and (t.get("output") or {}).get("summary"):
                        self.memory.store("fact", t["output"]["summary"][:600], {"task": t["title"], "citations": ",".join(t["output"].get("citations", [])[:5])}, run_id=run_id, importance=0.8)
            except Exception as e:
                self.db.event(run_id, "error", "memory", {"error": str(e)}, status="error")
        return {"result": result, "status": status}

    def deliver(self, state: RunState) -> dict:
        run_id = state["run_id"]
        self.db.update_run(run_id, status=state["status"], result=state.get("result"), error=state.get("error"))
        self.db.event(run_id, "delivered", "graph", {"status": state["status"]})
        return {}

    # ------------------------------------------------------------------ wiring ------------------
    def _route_after_plan(self, state: RunState) -> str:
        return "deliver" if state.get("status") == "failed" else "execute"

    def _route_after_execute(self, state: RunState) -> str:
        if state.get("to_review"):
            return "review"
        tasks = state["tasks"]
        if any(t["status"] in ("pending", "rejected") for t in tasks) and self._ready(tasks):
            return "execute"
        return "synthesize"

    def _route_after_review(self, state: RunState) -> str:
        tasks = state["tasks"]
        if self._ready(tasks):
            return "execute"
        if any(t["status"] == "review" for t in tasks):
            return "review"
        return "synthesize"

    def _build(self):
        g = StateGraph(RunState)
        for name in ("intake", "plan", "execute", "review", "synthesize", "deliver"):
            g.add_node(name, self._timed(getattr(self, name)))
        g.add_edge(START, "intake")
        g.add_edge("intake", "plan")
        g.add_conditional_edges("plan", self._route_after_plan, {"deliver": "deliver", "execute": "execute"})
        g.add_conditional_edges("execute", self._route_after_execute, {"review": "review", "execute": "execute", "synthesize": "synthesize"})
        g.add_conditional_edges("review", self._route_after_review, {"execute": "execute", "review": "review", "synthesize": "synthesize"})
        g.add_edge("synthesize", "deliver")
        g.add_edge("deliver", END)
        return g.compile(checkpointer=self.saver)

    # ------------------------------------------------------------------ public API ---------------
    def config(self, run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}, "recursion_limit": self.s.max_steps + 20}

    def start(self, run: dict) -> dict:
        state: RunState = {"run_id": run["run_id"], "request": run["request"], "options": run.get("options") or {}, "started": time.time(), "step": 0}
        return self._invoke(run["run_id"], state)

    def resume(self, run_id: str, decision: dict | None) -> dict:
        from langgraph.types import Command
        return self._invoke(run_id, Command(resume=decision) if decision is not None else None)

    def _invoke(self, run_id: str, inp) -> dict:
        try:
            out = self.graph.invoke(inp, self.config(run_id))
        except BudgetExhausted as e:
            self.db.update_run(run_id, status="paused_budget", error=str(e))
            self.db.event(run_id, "budget", "graph", {"reason": str(e)}, status="paused")
            return {"status": "paused_budget", "error": str(e)}
        if "__interrupt__" in out and out["__interrupt__"]:
            intr = out["__interrupt__"][0].value
            self.db.update_run(run_id, status="paused_for_approval")
            return {"status": "paused_for_approval", "interrupt": intr}
        final = self.db.get_run(run_id)
        return {"status": final["status"], "result": final.get("result"), "error": final.get("error")}
