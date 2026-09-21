"""The feature under test: classify a support email into billing / technical / account /
general (and, on the LLM backend, write a one-sentence summary). The prompt is a versioned,
configurable parameter. Two backends share the same contract:

  openai  — any OpenAI-compatible chat endpoint; the model writes JSON that we parse and validate.
  jev     — TypeSafe's System One model (POST /v1/systemone): one Choice question whose options
            are the four categories. The answer is typed, so there is nothing to parse; every
            answer also carries a probability per category and a confidence score. Jev does not
            generate text, so the summary dimension is "not applicable" on this backend."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, model_validator

Category = Literal["billing", "technical", "account", "general"]
CATEGORIES = ("billing", "technical", "account", "general")


class Classification(BaseModel):
    """Interface contract (guide Phase 1.3): structured, typed output. `summary` is None only on
    the jev backend, which cannot generate text; the openai parser still requires it."""
    category: Category
    summary: str | None = Field(default=None, min_length=5, max_length=300)


Backend = Literal["openai", "jev"]


class PromptConfig(BaseModel):
    version: str
    created: datetime
    description: str = ""
    backend: Backend = "openai"
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int = 200
    system_prompt: str = ""
    few_shot: list[dict] = []           # [{"email": ..., "category": ..., "summary": ...}]
    # jev backend: one Choice question. `instructions` and each criteria value may be a string or
    # JSON structure (TypeSafe "Advanced: structure"); `state_context` wraps the email in an object.
    instructions: Any = None
    criteria: dict[str, Any] | None = None
    state_context: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_backend(self) -> "PromptConfig":
        if self.backend == "openai" and not self.system_prompt:
            raise ValueError("openai backend needs system_prompt")
        if self.backend == "jev":
            if not self.criteria or set(self.criteria) != set(CATEGORIES):
                raise ValueError(f"jev backend needs criteria with exactly the keys {CATEGORIES}")
            if self.instructions is None and not self.system_prompt:
                raise ValueError("jev backend needs instructions (or system_prompt)")
        return self

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

    def jev_question(self) -> dict:
        """The Choice question sent to TypeSafe. Option names are the category labels; the
        descriptions are the versioned part a prompt change edits."""
        return {"type": "choice", "instructions": self.instructions if self.instructions is not None else self.system_prompt,
                "criteria": self.criteria}

    def jev_state(self, email: str) -> Any:
        return {**self.state_context, "email": email} if self.state_context else email


@dataclass
class FeatureResult:
    raw_output: str
    parsed: Classification | None
    validation_error: str | None
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    model: str
    confidence: float | None = None          # jev only: 0–1, derived from the probability spread
    probabilities: dict[str, float] | None = None   # jev only: probability per category


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
    if "summary" not in data:
        return None, "schema: summary: field required"
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


class JevClassifier:
    """TypeSafe System One backend. One HTTP call per email, one Choice question, typed answer.
    429s are retried honouring `retry-after`; any other failure is recorded as a failed case."""
    ENDPOINT = "/v1/systemone"

    def __init__(self, api_key: str, default_model: str = "jev-latest", base_url: str = "https://api.typesafe.ai",
                 timeout: float = 30.0, max_retries: int = 3, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ValueError("REG_TYPESAFE_API_KEY (or TYPESAFE_API_KEY) is not set")
        self.client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport,
                                   headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        self.default_model = default_model
        self.max_retries = max_retries

    def request_body(self, email: str, cfg: PromptConfig) -> dict:
        return {"state": cfg.jev_state(email), "model": cfg.model or self.default_model, "questions": {"category": cfg.jev_question()}}

    def _post(self, body: dict) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            resp = self.client.post(self.ENDPOINT, json=body)
            if resp.status_code != 429 or attempt == self.max_retries:
                return resp
            time.sleep(float(resp.headers.get("retry-after", 2 ** attempt)))
        return resp  # pragma: no cover

    def classify(self, email: str, cfg: PromptConfig) -> FeatureResult:
        body = self.request_body(email, cfg)
        model = body["model"]
        t0 = time.perf_counter()
        try:
            resp = self._post(body)
            latency = round((time.perf_counter() - t0) * 1000, 1)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return FeatureResult(f"ERROR: {e}", None, f"request failed: {type(e).__name__}", round((time.perf_counter() - t0) * 1000, 1), None, None, model)
        ans = data.get("answers", {}).get("category") or {}
        usage = data.get("usage") or {}
        raw = json.dumps(ans, ensure_ascii=False)
        served = data.get("model") or model
        try:
            parsed = Classification(category=ans["choice"])
        except (KeyError, ValidationError) as e:
            return FeatureResult(raw, None, f"schema: {e}", latency, usage.get("input_tokens"), usage.get("output_tokens"), served)
        return FeatureResult(raw, parsed, None, latency, usage.get("input_tokens"), usage.get("output_tokens"), served,
                             confidence=ans.get("confidence"), probabilities=ans.get("probabilities"))

    def list_models(self) -> list[dict]:
        resp = self.client.get("/v1/models")
        resp.raise_for_status()
        return resp.json().get("models", [])


def make_classifier(cfg: PromptConfig, settings) -> "Classifier | JevClassifier":
    if cfg.backend == "jev":
        return JevClassifier(settings.typesafe_api_key, settings.jev_model, settings.typesafe_base_url, settings.jev_timeout_s)
    return Classifier(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_s)
