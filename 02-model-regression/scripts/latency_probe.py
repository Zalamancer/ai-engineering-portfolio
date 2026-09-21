"""One-email latency probe across providers, same system prompt (prompts/v2.yaml) and the same
email. Reports every try so a cold first call is visible, then the median. Keys come from .env:
REG_TYPESAFE_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, XAI_API_KEY. Numbers are one laptop, one
moment — they show the shape (typed decision vs generated text), not a benchmark.

  uv run --group probe python scripts/latency_probe.py [--tries 3] [--email "..."]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import yaml  # noqa: E402

SYSTEM = yaml.safe_load((ROOT / "prompts" / "v2.yaml").read_text())["system_prompt"]
DEFAULT_EMAIL = "The invoice PDF from May won't download — the link gives a 404. I need it for expenses."


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return (time.perf_counter() - t0) * 1000, out


def probe_jev(email):
    from regress.config import settings
    from regress.feature import JevClassifier, PromptConfig
    cfg = PromptConfig.load(ROOT / "prompts" / "jev-v4.yaml")
    clf = JevClassifier(settings.typesafe_api_key, settings.jev_model)
    def call():
        r = clf.classify(email, cfg)
        return f"{r.parsed.category if r.parsed else r.validation_error} (conf {r.confidence})", r.prompt_tokens, r.completion_tokens
    return call


def probe_anthropic(model, email, **kw):
    import anthropic
    client = anthropic.Anthropic()
    def call():
        r = client.messages.create(model=model, max_tokens=200, system=SYSTEM, messages=[{"role": "user", "content": email}], **kw)
        text = "".join(b.text for b in r.content if b.type == "text")
        return text.strip(), r.usage.input_tokens, r.usage.output_tokens
    return call


def probe_gemini(model, email, thinking_level=None):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    cfg = dict(system_instruction=SYSTEM, max_output_tokens=400)
    if thinking_level:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
    def call():
        r = client.models.generate_content(model=model, contents=email, config=types.GenerateContentConfig(**cfg))
        u = r.usage_metadata
        return (r.text or "").strip(), u.prompt_token_count, (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
    return call


def probe_openai_compat(model, email, base_url, key_env, **kw):
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=os.environ[key_env])
    def call():
        r = client.chat.completions.create(model=model, max_tokens=400, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": email}], **kw)
        u = r.usage
        return (r.choices[0].message.content or "").strip(), u.prompt_tokens, u.completion_tokens
    return call


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--email", default=DEFAULT_EMAIL)
    ap.add_argument("--only", help="substring filter on the probe name")
    args = ap.parse_args()
    e = args.email
    probes = [
        ("jev-1.13.0 (jev-v4, typed choice)", probe_jev(e)),
        ("claude-haiku-4-5", probe_anthropic("claude-haiku-4-5", e)),
        ("claude-sonnet-5 (effort low)", probe_anthropic("claude-sonnet-5", e, output_config={"effort": "low"})),
        ("claude-opus-5 (effort low)", probe_anthropic("claude-opus-5", e, output_config={"effort": "low"})),
        ("gemini-3.8-flash (default thinking)", probe_gemini("gemini-3.8-flash", e)),
        ("gemini-3.8-flash (thinking low)", probe_gemini("gemini-3.8-flash", e, thinking_level="low")),
        ("gemini-3.5-flash-lite", probe_gemini("gemini-3.5-flash-lite", e)),
        ("grok-4.20-non-reasoning", probe_openai_compat("grok-4.20-0309-non-reasoning", e, "https://api.x.ai/v1", "XAI_API_KEY")),
        ("grok-4.6", probe_openai_compat("grok-4.6", e, "https://api.x.ai/v1", "XAI_API_KEY")),
    ]
    rows = []
    for name, call in probes:
        if args.only and args.only not in name:
            continue
        lat, out, err = [], None, None
        for _ in range(args.tries):
            try:
                ms, out = timed(call)
                lat.append(ms)
            except Exception as ex:  # keep going; a failed provider is a row, not a crash
                err = f"{type(ex).__name__}: {str(ex)[:160]}"
                break
        if err:
            rows.append({"probe": name, "error": err, "tries_ms": [round(x) for x in lat]})
            print(f"{name:<40} ERROR {err}")
            continue
        text, tin, tout = out
        rows.append({"probe": name, "tries_ms": [round(x) for x in lat], "median_ms": round(statistics.median(lat)),
                     "min_ms": round(min(lat)), "input_tokens": tin, "output_tokens": tout, "output": text[:200]})
        print(f"{name:<40} tries {[round(x) for x in lat]} ms  median {round(statistics.median(lat)):>5} ms  "
              f"tokens {tin}/{tout}  → {text[:90]!r}")
    out_path = ROOT / "runs" / f"latency_probe_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps({"email": e, "system_prompt": "prompts/v2.yaml", "tries": args.tries, "rows": rows}, indent=1))
    print("saved", out_path)


if __name__ == "__main__":
    main()
