"""OpenAI-compatible chat client with budget accounting, plus a scripted FakeLLM for tests.
Every real call goes through the usage ledger: reserve → call → reconcile (guide/prompt requirement)."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .config import Settings


class BudgetExhausted(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    latency_ms: float
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float
    model: str


class LLM:
    def __init__(self, settings: Settings, db, run_id: str | None = None, model: str | None = None, bedrock_client=None):
        self.s = settings
        self.db = db
        self.run_id = run_id
        self.model = model or settings.llm_model
        self.provider = settings.llm_provider
        if self.provider == "bedrock":
            self.bedrock = bedrock_client or self._bedrock_client(settings)
            self.client = None
        else:
            self.bedrock = None
            self.client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=settings.llm_timeout_s, max_retries=1)
        self.calls = 0
        self.tokens = 0

    @staticmethod
    def _bedrock_client(settings: Settings):
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name=settings.bedrock_profile or None, region_name=settings.bedrock_region)
        return session.client("bedrock-runtime", config=Config(read_timeout=settings.llm_timeout_s, retries={"max_attempts": 2}))

    def is_available(self) -> bool:
        if self.provider == "bedrock":
            return self.bedrock is not None
        try:
            import httpx
            return httpx.get(self.s.llm_base_url.rstrip("/") + "/models", timeout=3.0,
                             headers={"Authorization": f"Bearer {self.s.llm_api_key}"}).status_code < 500
        except Exception:
            return False

    def _complete(self, messages: list[dict], max_tokens: int, temperature: float) -> tuple[str, int | None, int | None]:
        """Provider-specific call → (text, tokens_in, tokens_out)."""
        if self.provider == "bedrock":
            system = [{"text": m["content"]} for m in messages if m["role"] == "system"]
            convo = [{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages if m["role"] != "system"]
            kw = {"modelId": self.model, "messages": convo, "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature}}
            if system:
                kw["system"] = system
            resp = self.bedrock.converse(**kw)
            text = "".join(c.get("text", "") for c in resp["output"]["message"]["content"]).strip()
            u = resp.get("usage", {})
            return text, u.get("inputTokens"), u.get("outputTokens")
        resp = self.client.chat.completions.create(model=self.model, messages=messages, max_tokens=max_tokens, temperature=temperature)
        text = (resp.choices[0].message.content or "").strip()
        u = getattr(resp, "usage", None)
        return text, (u.prompt_tokens if u else None), (u.completion_tokens if u else None)

    def _price(self, tin: int, tout: int) -> float:
        return tin / 1000 * self.s.price_in_per_1k + tout / 1000 * self.s.price_out_per_1k

    def chat(self, messages: list[dict], max_tokens: int = 700, temperature: float = 0.0, agent: str = "llm", task_id: str | None = None) -> LLMResult:
        # ---- hard limits in code ----------------------------------------------------------
        if self.calls >= self.s.max_llm_calls:
            raise BudgetExhausted(f"max_llm_calls={self.s.max_llm_calls} reached")
        if self.tokens >= self.s.max_tokens_total:
            raise BudgetExhausted(f"max_tokens_total={self.s.max_tokens_total} reached")
        totals = self.db.ledger_totals() if self.db else {"committed": 0.0}
        reserve_usd = self._price(self.s.reserve_tokens_per_call, max_tokens)
        if totals["committed"] + reserve_usd > self.s.app_allowance_usd:
            raise BudgetExhausted(f"app allowance ${self.s.app_allowance_usd} exhausted (committed ${totals['committed']:.4f})")
        if self.run_id and self.db:
            run_tot = self.db.ledger_totals(self.run_id)
            if run_tot["committed"] + reserve_usd > self.s.max_cost_usd:
                raise BudgetExhausted(f"run cost cap ${self.s.max_cost_usd} reached")
        entry = self.db.reserve(self.run_id, "llm", reserve_usd, agent) if (self.db and self.run_id) else None

        t0 = time.perf_counter()
        text, tin, tout = self._complete(messages, max_tokens, temperature)
        latency = (time.perf_counter() - t0) * 1000
        cost = self._price(tin or 0, tout or 0)
        self.calls += 1
        self.tokens += (tin or 0) + (tout or 0)
        if entry:
            self.db.reconcile(entry, cost, tin, tout)
        if self.db and self.run_id:
            self.db.event(self.run_id, "llm_call", agent, {"model": self.model, "messages": messages, "response": text},
                          task_id=task_id, latency_ms=round(latency, 1), tokens_in=tin, tokens_out=tout, cost_usd=cost)
        return LLMResult(text, round(latency, 1), tin, tout, cost, self.model)


_JSON_RE = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> Any:
    """Pull the first JSON object out of a model reply (tolerates prose and ``` fences)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = text.replace("```json", "```").strip()
    if "```" in text:
        parts = [p for p in text.split("```") if p.strip().startswith("{")]
        if parts:
            text = parts[0]
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        # small models often append a stray brace or prose after the object: take the first complete object
        obj, _end = json.JSONDecoder().raw_decode(text[start:])
        return obj


class FakeLLM:
    """Scripted responses for tests: a list of (substring_of_prompt, reply) rules checked in order,
    or a queue of replies. Also honours the same budget counters so budget tests are real."""

    def __init__(self, rules: list[tuple[str, str]] | None = None, queue: list[str] | None = None, settings: Settings | None = None,
                 db=None, run_id: str | None = None):
        self.rules = rules or []
        self.queue = list(queue or [])
        self.s = settings
        self.db = db
        self.run_id = run_id
        self.calls = 0
        self.tokens = 0
        self.model = "fake-llm"
        self.history: list[list[dict]] = []

    def is_available(self) -> bool:
        return True

    def chat(self, messages, max_tokens=700, temperature=0.0, agent="llm", task_id=None) -> LLMResult:
        if self.s and self.calls >= self.s.max_llm_calls:
            raise BudgetExhausted(f"max_llm_calls={self.s.max_llm_calls} reached")
        self.history.append(messages)
        joined = "\n".join(m["content"] for m in messages)
        reply = None
        for needle, r in self.rules:
            if needle in joined:
                reply = r
                break
        if reply is None:
            reply = self.queue.pop(0) if self.queue else '{"final": "no scripted reply"}'
        self.calls += 1
        self.tokens += 50
        if self.db and self.run_id:
            self.db.event(self.run_id, "llm_call", agent, {"model": self.model, "messages": messages, "response": reply},
                          task_id=task_id, latency_ms=1.0, tokens_in=40, tokens_out=10, cost_usd=0.0)
        return LLMResult(reply, 1.0, 40, 10, 0.0, self.model)
