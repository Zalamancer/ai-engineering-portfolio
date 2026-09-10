"""Thin chat-completion client for any OpenAI-compatible endpoint.

Default: a local ``mlx_lm.server`` running Qwen3-4B-Instruct (Apache-2.0) on the Mac —
free, offline, no key. Point RAG_LLM_BASE_URL/RAG_LLM_API_KEY at OpenAI (or any other
compatible provider) to swap models without code changes.

Adaptation from the guide (GPT-4o / Claude Sonnet): no paid API is authorised for this
project. A 4B local model is noticeably weaker; results are labelled with the model used.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
from openai import OpenAI

from .config import Settings


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict = field(default_factory=dict)


class LLMClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.model = settings.llm_model
        self.client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key,
                             timeout=settings.llm_timeout_s, max_retries=1)

    def is_available(self) -> bool:
        try:
            r = httpx.get(self.s.llm_base_url.rstrip("/") + "/models", timeout=3.0,
                          headers={"Authorization": f"Bearer {self.s.llm_api_key}"})
            return r.status_code < 500
        except Exception:
            return False

    def chat(self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None,
             stop: list[str] | None = None) -> LLMResponse:
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages,
            max_tokens=max_tokens or self.s.llm_max_tokens,
            temperature=self.s.llm_temperature if temperature is None else temperature,
            stop=stop,
        )
        latency = (time.perf_counter() - t0) * 1000
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text, model=resp.model or self.model, latency_ms=round(latency, 1),
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
        )


class FakeLLM:
    """Deterministic stand-in for tests: answers are chosen by substring rules.
    Never used for quality measurements (mocks verify plumbing, not model quality)."""

    def __init__(self, rules: list[tuple[str, str]] | None = None, default: str = "STATUS: insufficient\nANSWER:\nI could not find this in the provided context."):
        self.rules = rules or []
        self.default = default
        self.calls: list[list[dict]] = []
        self.model = "fake-llm"

    def is_available(self) -> bool:
        return True

    def chat(self, messages, max_tokens=None, temperature=None, stop=None) -> LLMResponse:
        self.calls.append(messages)
        text = " ".join(m["content"] for m in messages)
        for needle, reply in self.rules:
            if needle in text:
                return LLMResponse(reply, self.model, 0.1, 10, 10)
        return LLMResponse(self.default, self.model, 0.1, 10, 10)
