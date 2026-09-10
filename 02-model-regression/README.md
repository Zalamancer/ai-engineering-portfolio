# 02 · Model regression detection for an LLM support-email classifier

Guide project #1 (BASWE "15 AI Engineering Projects", pp. 3–5). A CI-style pipeline that runs a
golden dataset through an LLM feature every time a prompt changes, scores the outputs on several
dimensions, diffs the run against a saved baseline, produces an HTML report and score history,
raises pass / warn / critical verdicts and slow-drift warnings, builds Slack alerts, and blocks
a merge on a critical regression.

**The feature under test:** classify a customer-support email into `billing | technical |
account | general` and write a one-sentence summary, returned as validated JSON. The prompt is a
versioned YAML file — that is the "code" the pipeline runs regression checks against.

Written like onboarding docs for a teammate, not a tutorial.

## What it does in one paragraph

`regress run --prompt prompts/v2.yaml --gate` loads the prompt config and the golden dataset,
sends every case to the model (bounded concurrency), validates each output against a Pydantic
schema, checks the category, asks an LLM judge to score the summary 1–5, records latency and
token usage, stores everything in SQLite + JSON, compares against the latest baseline run
(pass-rate delta, per-category accuracy delta, the exact cases that regressed or improved), applies
the policy thresholds, checks the 7-run moving average for slow drift, renders an HTML report
with a trend chart, builds a Slack message (sent only with `--send` and a configured webhook),
and exits non-zero on a critical regression.

## Setup

```bash
cd 02-model-regression
uv sync
# model endpoint: any OpenAI-compatible server. Default = the local mlx_lm server from project 1:
../01-hybrid-rag/scripts/serve_llm.sh        # in another terminal
cp .env.example .env                         # optional overrides
uv run pytest -q                             # 12 tests, no model needed
uv run regress dataset-stats
uv run regress run --prompt prompts/v1.yaml --set-baseline
uv run regress run --prompt prompts/v2.yaml --gate
uv run regress run --prompt prompts/v3-bad.yaml --gate   # intentionally bad → exit code 2
uv run regress history
open reports/<run_id>.html
```

Docker: `docker build -t regress . && docker run --rm -e REG_LLM_BASE_URL=... -e REG_LLM_API_KEY=... -v $PWD/runs:/app/runs -v $PWD/reports:/app/reports regress run --prompt prompts/v2.yaml --gate`
(image written, not built on this Mac — see limitations).

## Layout

```
prompts/            versioned prompt configs (version, timestamp, system prompt, few-shot); v3-bad is the demo failure
data/golden/golden.json   80 cases: id, input, expected category + summary, difficulty, tags, notes, verification
regress/feature.py  the classifier + PromptConfig + Pydantic output contract
regress/scoring.py  category match · JSON validity · summary judge (1–5) · latency · tokens
regress/runner.py   async batched run, aggregation (per category / per difficulty, p50/p95 latency)
regress/compare.py  baseline diff: deltas, regressed/improved cases, POLICY verdict, McNemar exact test + Wilson CIs
regress/drift.py    7-run moving-average drift warning
regress/report.py   HTML report (scorecard, side-by-side regressions, inline SVG trend)
regress/alerts.py   Slack Block Kit payload; outbox unless --send + webhook
regress/storage.py  SQLite (runs, case_results) + runs/<id>/{summary,cases,comparison}.json
regress/cli.py      `regress run | compare | history | dataset-stats | set-baseline`
scripts/review_ui.py  human review screen for the golden dataset
scripts/demo_runs.sh  baseline → candidate → bad prompt
.github/workflows/regression.yml   PR gate on prompts/**
```

## How to add golden cases

Append to `data/golden/golden.json` with a new stable `id`, the raw email, the correct
category, an ideal one-sentence summary, `expected_difficulty`, tags (`mixed`, `short`,
`typos`, `mixed-language`, `sarcasm`, `angry`) and a `notes` line saying why the case matters.
Bump `version`. Cases you did not label yourself must carry
`"verification": {"status": "ai_generated"}` until a person verifies them in the review UI —
runs record the verified count (`n_verified`) and label the dataset accordingly.

**Current state of the dataset: all 80 cases were drafted by an AI as review candidates.
They are not yet human-verified and do not satisfy the guide's "hand-written, human-verified"
requirement until Ihsan reviews them** (`uv run streamlit run scripts/review_ui.py`).
Pass `--only-verified` to score only verified cases.

## How to adjust thresholds

Environment variables (or `.env`): `REG_WARN_DELTA` (default 0.03), `REG_CRITICAL_DELTA` (0.08),
`REG_SUMMARY_PASS_SCORE` (4), `REG_DRIFT_WINDOW` (7), `REG_DRIFT_THRESHOLD` (0.85).

These are **policy thresholds**, not statistical significance — the guide calls them
"statistical significance", we do not. Each comparison additionally reports the number of
cases that flipped each way, an exact two-sided binomial (McNemar) p-value on the discordant
pairs, and 95 % Wilson intervals for both pass rates. With 80 cases the interval on a 90 % pass
rate is roughly ±7 pp, so a 3 pp change is almost never distinguishable from noise; the
verdict says what the team decided to act on, the statistics say how sure you can be.

## Architecture decisions

- **Prompt = versioned artifact.** YAML with `version`, `created`, `description`, optional
  `model`, temperature, system prompt, few-shot examples. The run records the version and the
  dataset content fingerprint, so any two runs can be compared knowing exactly what changed.
- **Pass = category correct ∧ output valid ∧ summary judged ≥ 4.** Invalid JSON is a failure, not a
  crash. When the judge is disabled, the summary dimension is "not judged" and pass falls back
  to category + validity (recorded as such).
- **Regressions are listed by case, not just by rate.** The side-by-side table of old vs new
  output is the thing a reviewer actually reads.
- **Drift is separate from per-run diffs.** A run can pass every gate while the 7-run moving
  average slides under the threshold; the drift check catches that.
- **Alerts never leave the machine by default.** The payload is always built and saved to
  `alerts/outbox/`; delivery requires both `REG_SLACK_WEBHOOK_URL` and `--send`. Live delivery
  is **pending** until a test channel is authorised.
- **CI is honest about missing model access.** The workflow always runs tests and validation;
  the eval step runs only when `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` secrets exist, otherwise the
  PR comment says the gate was skipped — never that it passed.
- **SQLite + JSON.** Zero infrastructure; `runs/` can be committed so CI has a baseline.

## Results

Model under test and judge: local Qwen3-4B (no paid API). Judge scores are model judgments. LLM server was
shared with other evaluation jobs, so latencies are inflated. Reports: `reports/*.html`; per-case outputs and
comparisons: `runs/<run_id>/`.

### On the human-verified dataset (0.2.0-reviewed, 80 cases reviewed by Ihsan Duru, 6 labels corrected)

| run | prompt | pass rate | category acc | output valid | p50 latency | verdict vs baseline | flipped cases | exact p (McNemar) |
|---|---|---|---|---|---|---|---|---|
| 20260909-193113_v1 | v1 baseline | 85.0 % | 87.5 % | 100 % | 5.0 s | baseline | – | – |
| 20260909-193704_v2 | v2 + tie-break rules + 3 few-shots | 82.5 % | 82.5 % | 100 % | 5.3 s | **PASS** (−2.5 pp, under the 3 pp warning line) | 4 regressions / 2 improvements | 0.688 (noise-consistent) |
| 20260909-194336_v3-bad | v3-bad (definitions removed, biased to "general") | 23.8 % | 23.8 % | 100 % | 4.9 s | **CRITICAL** (−61.3 pp > 8 pp), gate exit code 2 | 50 regressions / 1 improvement | < 0.001 |

v2's four regressions are all billing emails re-labelled *general* (c008 "hi. receipt pls", c015, c017, c020): the new
tie-break rule "unclear → general" over-fires on short billing requests; billing accuracy fell 25 pp while the other three
categories were unchanged. A real team would reword rule 4 and re-run. v3-bad collapsed account (−82 pp), billing (−88 pp)
and technical (−83 pp) into "general", exactly the failure the gate exists to stop.

### Same prompts on the earlier AI-drafted labels (0.1.0-ai-draft) — kept for comparison

| prompt | pass rate | verdict vs its baseline |
|---|---|---|
| v1 | 86.3 % | baseline |
| v2 | 82.5 % | WARN (−3.8 pp) |
| v3-bad | 25.0 % | CRITICAL (−61.3 pp) |

Note how the v2 verdict moved from WARN to PASS once a human corrected six labels: with n = 80 the verdict near a 3 pp
line is sensitive to a handful of labels, which is why the report shows the exact p-value (0.69 here) and Wilson intervals
(baseline 75–91 %) next to the policy verdict rather than calling the threshold "significance".

Drift check: needs 7 runs of one prompt version; correctly reports "need 7 runs". Slack: payloads for every run are built
and saved in `alerts/outbox/`; none sent (no webhook authorised).

## Limitations

- Dataset AI-drafted, pending human verification (see above).
- Judge = same 4B model as the feature; a stronger, separate judge would be better.
- No GitHub repository connected yet, so the Actions workflow has not executed remotely; GitHub
  Actions inference would need an API key or a reachable model endpoint as a secret.
- Slack delivery not exercised live.
- Docker image not built here (disk).
