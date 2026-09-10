"""Supervisor / specialist / reviewer prompts and their structured-output contracts."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .llm import extract_json

SPECIALISTS = ("research", "analysis", "writing")


class PlanTask(BaseModel):
    idx: int = Field(ge=1, le=8)
    title: str = Field(min_length=3, max_length=120)
    specialist: Literal["research", "analysis", "writing"]
    description: str = Field(min_length=10, max_length=1200)
    depends_on: list[int] = []
    inputs: list[str] = []
    expected_output: str = Field(default="", max_length=400)
    complexity: Literal["low", "medium", "high"] = "medium"


class Plan(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=800)
    tasks: list[PlanTask] = Field(min_length=1, max_length=8)

    @field_validator("tasks")
    @classmethod
    def valid_dag(cls, tasks):
        idxs = {t.idx for t in tasks}
        if len(idxs) != len(tasks):
            raise ValueError("duplicate task idx")
        for t in tasks:
            for d in t.depends_on:
                if d not in idxs:
                    raise ValueError(f"task {t.idx} depends on unknown task {d}")
                if d >= t.idx:
                    raise ValueError(f"task {t.idx} may only depend on earlier tasks (got {d})")
        return tasks


class ReviewVerdict(BaseModel):
    verdict: Literal["accept", "reject"]
    score: int = Field(ge=1, le=5)
    feedback: str = Field(default="", max_length=1200)
    issues: list[str] = []


SUPERVISOR_PROMPT = """You are the SUPERVISOR of a small team of specialist agents: research (searches documentation/web and extracts facts with sources), analysis (runs Python or read-only SQL over data, computes numbers), writing (produces the final written deliverable and can post it to the team webhook).

Break the user's request into 1-6 ordered tasks. Each task is assigned to exactly one specialist and lists the earlier tasks whose output it needs. Keep it minimal: no task that the request does not require.
{memory_block}
Reply with ONLY a JSON object:
{{"confidence": <0-1, how sure you are this plan fully satisfies the request>,
 "rationale": "<one or two sentences>",
 "tasks": [{{"idx": 1, "title": "...", "specialist": "research|analysis|writing", "description": "<what exactly to do and what to hand over>",
            "depends_on": [], "inputs": ["<which earlier outputs to use>"], "expected_output": "<format of the output>", "complexity": "low|medium|high"}}]}}

USER REQUEST:
{request}"""

SPECIALIST_PROMPT = """You are the {specialist} specialist. Complete the task below using the tools available to you, then return a final result.

TASK: {title}
{description}
Expected output: {expected_output}
{inputs_block}{feedback_block}
TOOLS (call at most one per turn; args must match the schema):
{tools}

Turns used: {turn}/{max_turns}. When you have enough, return the final result.

Reply with ONLY one JSON object, either
{{"thought": "<brief>", "action": {{"tool": "<name>", "args": {{...}}}}}}
or
{{"thought": "<brief>", "final": {{"summary": "<2-3 sentences>", "content": "<the full deliverable text>", "citations": ["<url or doc id of every source you relied on>"]}}}}

Rules: only state facts you found in tool results or dependency outputs; list every source URL you used in citations; if a tool fails, try a different approach or return what you have and say what is missing.
{history}"""

REVIEWER_PROMPT = """You are the REVIEWER. Check the specialist's output against its task before it goes to the supervisor.

TASK ({specialist}): {title}
{description}
Expected output: {expected_output}

SPECIALIST OUTPUT:
{output}

EVIDENCE THE SPECIALIST ACTUALLY RETRIEVED (tool results, abridged):
{evidence}

Reject if: the output does not do what the task asked, claims facts that do not appear in the evidence, cites sources that were not retrieved, or is incomplete. Otherwise accept. Score 1-5 for quality.
Reply with ONLY JSON: {{"verdict": "accept|reject", "score": <1-5>, "feedback": "<what to fix, specific>", "issues": ["..."]}}"""

SYNTHESIS_PROMPT = """You are the SUPERVISOR. Assemble the final deliverable for the user from the completed tasks. Keep every citation. Do not add facts that are not in the task outputs.

USER REQUEST: {request}

TASK OUTPUTS:
{outputs}

Reply with ONLY JSON: {{"report": "<final markdown report>", "citations": ["<all source urls/doc ids>"], "caveats": ["<anything missing or uncertain>"]}}"""


def parse_plan(text: str) -> Plan:
    return Plan(**extract_json(text))


def parse_review(text: str) -> ReviewVerdict:
    return ReviewVerdict(**extract_json(text))


def parse_specialist(text: str) -> dict:
    obj = extract_json(text)
    if "action" in obj:
        a = obj["action"]
        if not isinstance(a, dict) or "tool" not in a:
            raise ValueError("action must have a tool name")
        a.setdefault("args", {})
        return {"kind": "action", "thought": obj.get("thought", ""), "tool": a["tool"], "args": a["args"] or {}}
    if "final" in obj:
        f = obj["final"] if isinstance(obj["final"], dict) else {"content": str(obj["final"])}
        return {"kind": "final", "thought": obj.get("thought", ""),
                "output": {"summary": str(f.get("summary", ""))[:1000], "content": str(f.get("content", ""))[:20000],
                           "citations": [str(c) for c in (f.get("citations") or [])][:30]}}
    raise ValueError("reply must contain 'action' or 'final'")


def clip(x, n: int = 1500) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + " …[truncated]"
