"""The LLM feature under test: classify a support email into billing / technical / account /
general and write a one-sentence summary. The prompt is a versioned, configurable parameter."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

Category = Literal["billing", "technical", "account", "general"]
CATEGORIES = ("billing", "technical", "account", "general")


class Classification(BaseModel):
    """Interface contract (guide Phase 1.3): structured, typed output."""
    category: Category
    summary: str = Field(min_length=5, max_length=300)


class PromptConfig(BaseModel):
    version: str
    created: datetime
    description: str = ""
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 200
    system_prompt: str
    few_shot: list[dict] = []           # [{"email": ..., "category": ..., "summary": ...}]

    @classmethod
    def load(cls, path: str | Path) -> "PromptConfig":
        data = yaml.safe_load(Path(path).read_text())
        cfg = cls(**data)
        cfg._path = str(path)  # type: ignore[attr-defined]
        return cfg

    def messages(self, email: str) -> list[dict]:
        msgs = [{"role": "system", "content": self.system_prompt}]
        for ex in self.few_shot:
            msgs.append({"role": "user", "content": ex["email"]})
            msgs.append({"role": "assistant", "content": json.dumps({"category": ex["category"], "summary": ex["summary"]})})
        msgs.append({"role": "user", "content": email})
        return msgs


@dataclass
class FeatureResult:
    raw_output: str
    parsed: Classification | None
    validation_error: str | None
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    model: str


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_output(text: str) -> tuple[Classification | None, str | None]:
    """Strict-ish parsing: find the JSON object, validate with Pydantic. Anything else is a failure."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = _JSON_RE.search(text)
    if not m:
        return None, "no JSON object in output"
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    if isinstance(data.get("category"), str):
        data["category"] = data["category"].strip().lower()
    try:
        return Classification(**data), None
    except ValidationError as e:
        return None, "schema: " + "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())


class Classifier:
    def __init__(self, base_url: str, api_key: str, default_model: str, timeout: float = 120.0):
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=1)
        self.default_model = default_model

    def classify(self, email: str, cfg: PromptConfig) -> FeatureResult:
        model = cfg.model or self.default_model
        t0 = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(model=model, messages=cfg.messages(email),
                                                       temperature=cfg.temperature, max_tokens=cfg.max_tokens)
            text = resp.choices[0].message.content or ""
            usage = resp.usage
            pt, ct = (usage.prompt_tokens, usage.completion_tokens) if usage else (None, None)
        except Exception as e:  # network / server error counts as a failure, not a crash
            return FeatureResult(f"ERROR: {e}", None, f"request failed: {type(e).__name__}", (time.perf_counter() - t0) * 1000, None, None, model)
        latency = (time.perf_counter() - t0) * 1000
        parsed, err = parse_output(text)
        return FeatureResult(text, parsed, err, round(latency, 1), pt, ct, model)
