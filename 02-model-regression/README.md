# 02 · Model regression detection for an LLM support-email classifier

Guide project #1 (BASWE "15 AI Engineering Projects", pp. 3–5). A CI-style pipeline that runs a
golden dataset through an LLM feature every time a prompt changes, scores the outputs on several
dimensions, diffs the run against a saved baseline, produces an HTML report and score history,
raises pass / warn / critical verdicts and slow-drift warnings, builds Slack alerts, and blocks
a merge on a critical regression.

**The feature under test:** classify a customer-support email into `billing | technical |
account | general` and write a one-sentence summary, returned as validated JSON. The prompt is a
versioned YAML file — that is the "code" the pipeline runs regression checks against.

**Two backends behind one contract** (2026-09-21): the original OpenAI-compatible LLM path, and
[TypeSafe's Jev](https://docs.typesafe.ai) — a "System One" model that answers one typed Choice
question per email with a probability per category and a confidence score, instead of generating
text. Same golden set, same scoring, same gate; see [Jev results](#jev-backend-typesafe-system-one).

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

# jev backend: put REG_TYPESAFE_API_KEY in .env (console.typesafe.ai/keys), then the same commands
uv run regress run --prompt prompts/jev-v1.yaml --set-baseline    # baselines are per backend
uv run regress run --prompt prompts/jev-v4.yaml --gate
uv run regress run --prompt prompts/jev-v4.yaml --model jev-preview --baseline <jev-v4 run id> --gate   # model swap under the same prompt
uv run regress run --prompt prompts/jev-v4.yaml --golden data/golden/holdout.json                       # held-out set, no auto-compare
uv run regress confidence-curve <jev run id>     # accuracy vs coverage if low-confidence emails go to a human
uv run regress versus <llm run id> <jev run id>  # cross-backend: accuracy per category, latency, tokens, $/1k emails
```

Docker: `docker build -t regress . && docker run --rm -e REG_LLM_BASE_URL=... -e REG_LLM_API_KEY=... -v $PWD/runs:/app/runs -v $PWD/reports:/app/reports regress run --prompt prompts/v2.yaml --gate`
(image written, not built on this Mac — see limitations).

## Layout

```
prompts/            versioned prompt configs (version, timestamp, system prompt, few-shot); v3-bad is the demo failure
                    jev-v1…v4: `backend: jev` configs — Choice instructions + per-category criteria (string or JSON structure)
data/golden/golden.json   80 cases: id, input, expected category + summary, difficulty, tags, notes, verification
data/golden/holdout.json  24 AI-drafted held-out cases written after jev-v4 was frozen (not human-verified)
regress/feature.py  the classifier + PromptConfig + Pydantic output contract; `Classifier` (LLM) and `JevClassifier` (TypeSafe)
regress/scoring.py  category match · JSON validity · summary judge (1–5) · latency · tokens
regress/runner.py   async batched run, aggregation (per category / per difficulty, p50/p95 latency)
regress/compare.py  baseline diff: deltas, regressed/improved cases, POLICY verdict, McNemar exact test + Wilson CIs
regress/drift.py    7-run moving-average drift warning
regress/report.py   HTML report (scorecard, side-by-side regressions, inline SVG trend)
regress/alerts.py   Slack Block Kit payload; outbox unless --send + webhook
regress/storage.py  SQLite (runs, case_results) + runs/<id>/{summary,cases,comparison}.json
regress/cli.py      `regress run | compare | history | dataset-stats | set-baseline | confidence-curve | versus`
scripts/review_ui.py  human review screen for the golden dataset
scripts/demo_runs.sh  baseline → candidate → bad prompt
(repo root) .github/workflows/regression.yml   PR gate on prompts/**
```

## How to add golden cases

Append to `data/golden/golden.json` with a new stable `id`, the raw email, the correct
category, an ideal one-sentence summary, `expected_difficulty`, tags (`mixed`, `short`,
`typos`, `mixed-language`, `sarcasm`, `angry`) and a `notes` line saying why the case matters.
Bump `version`. Cases you did not label yourself must carry
`"verification": {"status": "ai_generated"}` until a person verifies them in the review UI —
runs record the verified count (`n_verified`) and label the dataset accordingly.

**Dataset state: the 80 golden cases were drafted by an AI, then all 80 were reviewed by Ihsan
Duru (6 labels corrected) — version 0.2.0-reviewed is human-verified.** The 24-case
`holdout.json` is AI-drafted and unverified; runs label the dataset accordingly.
Pass `--only-verified` to score only verified cases; `--golden <file>` scores another file.

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

## Jev backend (TypeSafe System One)

**Why:** the LLM path spends ~5 s and a few hundred generated tokens per email to produce one
word we then parse and validate. Jev is built for exactly this shape of problem — "unstructured
state in, typed probabilistic decision out" — so the question was whether the same golden set
and gate would show it as faster *and* at least as accurate, and what the confidence score buys.

**How it is wired:** `backend: jev` in the prompt YAML. The email is the `state` (wrapped in an
object with company context from v2 on); the four categories are the options of one Choice
question; `instructions` and each option's description accept JSON structure, which is where the
team's boundary rules live. The answer is typed (`choice`, `probabilities`, `confidence`), so
`output_valid` is always 100 % and the summary dimension is **not applicable** — pass = category
correct. Baselines are per backend; a jev candidate is never diffed against an LLM run. The
served model id is recorded per run (`jev-1.13.0` behind the `jev-latest` alias).

### Improvement ledger — one change per version, each run gated against the jev-v1 baseline

Golden 0.2.0-reviewed, 80 human-verified cases, fingerprint d6f4a7d7d3be. Prices from docs.typesafe.ai/models on 2026-09-21 ($0.042 / Mtok input, output free).

| run | what changed | category acc | Δ vs jev-v1 | regressions / improvements | McNemar p | p50 / p95 | mean conf. on **wrong** answers | $ per 1k emails |
|---|---|---|---|---|---|---|---|---|
| 20260921-023002_jev-v1 | the v1 one-line category definitions as Choice options, plain-string state | **85.0 %** | baseline | – | – | 195 / 876 ms | 0.78 | $0.018 |
| 20260921-023053_jev-v2 | structured options (`covers` / `not`) + 5 tie-break rules + company context, written after reading v1's 12 failures | 91.3 % | +6.3 pp | 3 / 8 | 0.227 | 178 / 382 ms | 0.89 | $0.035 |
| 20260921-023143_jev-v3 | two rules v2 had backwards, rewritten from the labelling convention (malfunctioning login/2FA/billing feature → technical; price question → billing) | 93.8 % | +8.8 pp | 3 / 10 | 0.092 | 200 / 467 ms | 0.68 | $0.039 |
| 20260921-023228_jev-v4 | one clarification: *locked out and needs access restored* → account, whatever the cause | **97.5 %** | **+12.5 pp** | **0 / 10** | **0.002** | 189 / 376 ms | 0.64 | $0.042 |

Reading the ledger: every version was written after looking at the previous run's failure list
(all boundary cases — billing↔account, technical↔account, general↔technical), so the criteria
now encode this team's conventions, e.g. *"a 2FA code rejected as expired is a bug (technical);
a password rejected after a reset is a lockout (account)"*. v2 shows why the gate lists cases
and not just rates: +6 pp overall hid three new mistakes (a sarcastic "reverse my upgrade",
"student pricing?", "do you support Okta SSO?") that a later rule fixed. v3 fixed the
technical boundary but moved three "can't log in" emails to technical; v4 fixed that with zero
regressions. The two remaining errors (c005 "switch to annual billing, is there a discount?",
c058 "how many users on the Team plan?") are the reviewer's own coin-flips in the notes, and
Jev is least sure about exactly those (confidence 0.73 and 0.55 vs a 0.95 mean).

**Held-out check (`data/golden/holdout.json`, 24 cases, 6 per category, AI-drafted after v4
was frozen, not human-verified):** jev-v1 70.8 % → jev-v4 **95.8 %** (17/24 → 23/24; the miss is
"limit invites to our email domain", labelled account, answered general at 0.72). The criteria
were tuned on the 80 golden cases, so the +12.5 pp is an in-sample number; the held-out gain
(+25 pp on labels that follow the same convention) says the rules generalise rather than
memorise, with the caveat that those 24 labels are mine, not a reviewer's.

**Stability and model swap:** a repeat of jev-v4 flipped 0 of 80 cases (Jev is deterministic at
this setting); jev-v4 with `--model jev-preview` also flipped 0 (the alias currently points at
the same `jev-1.13.0`, as the docs say — the gate confirms it rather than trusting it). A
hand-set `--model` is how a team would run the gate the day an alias moves.

### LLM vs Jev on the same 80 cases (`regress versus 20260909-193113_v1 20260921-023228_jev-v4`)

| | LLM v1 (Qwen3-4B, local, `prompts/v1.yaml`) | Jev v4 (`jev-1.13.0`, `prompts/jev-v4.yaml`) |
|---|---|---|
| category accuracy | 87.5 % | **97.5 %** (Wilson 95 % 91.3–99.3 %) |
| billing / technical / account / general | 87.5 / 82.6 / 81.8 / 100 % | 100 / 100 / 90.9 / 100 % |
| cases only one side gets right | 0 | 8 (c006, c010, c013, c014, c029, c033, c049, c055); both wrong: c005, c058 |
| output valid | 100 % (after JSON parsing + schema) | 100 % by construction (typed answer) |
| one-sentence summary | yes, judged by the LLM | **not possible** — Jev does not generate text |
| latency p50 / p95 | 4,975 / 12,799 ms | **189 / 376 ms** (26× / 34× lower) |
| wall clock, 80 emails | 348 s (2 concurrent) | 2.2 s (8 concurrent) |
| tokens per email | 182 in + 33 out | 1,000 in + 45 out (the rules and criteria ride along with every call) |
| cost per 1k emails | local model, no API bill; ~70 min of a shared M-series Mac | $0.042 |
| confidence signal | none | per-category probabilities + confidence |

The latency numbers are not apples to apples — the LLM ran on a shared laptop, Jev on a hosted
API — but the shape is the point: the classifier stops being the slow step. The accuracy gain
is a prompt-engineering result as much as a model result: jev-v1 with the *same* definitions as
the LLM prompt was 85 %, below the LLM's 87.5 %; the structured rules are what took it to 97.5 %.

### What confidence buys: routing instead of guessing (`regress confidence-curve 20260921-023228_jev-v4`)

| act only when confidence ≥ | emails handled automatically | accuracy on those | sent to a human | wrong *and* auto-handled |
|---|---|---|---|---|
| 0.00 (never route) | 80 (100 %) | 97.5 % | 0 | 2 |
| 0.70 | 73 (91 %) | 98.6 % | 7 | 1 |
| **0.80** | **70 (88 %)** | **100 %** | **10** | **0** |
| 0.95 | 67 (84 %) | 100 % | 13 | 0 |

With a 0.80 threshold this team would auto-route 88 % of emails with no observed mistakes and
hand 10 of 80 to a person — including both of the cases the labellers themselves found ambiguous.
That is the TypeSafe confidence-gated-routing pattern measured on real cases rather than asserted.
Mean confidence on wrong answers fell from 0.78 (v1) to 0.64 (v4) while mean confidence on right
answers stayed at 0.95–0.97: better criteria made Jev not only more right but more honest about the rest.

### Limitations of the Jev results

- Criteria tuned and evaluated on the same 80 cases; the 24 held-out cases are AI-drafted and
  unverified. A second human-reviewed set is the next step before quoting 97.5 % as expected accuracy.
- n = 80: the Wilson interval on 97.5 % is 91–99 %; on the held-out 95.8 % it is 80–99 %.
- No summary on this backend. A production design would keep Jev for routing and call an LLM
  for the summary only where a summary is needed, or drop the summary dimension.
- Latency measured from a laptop over the public internet to a hosted API; the LLM latency is a
  4B model on a shared Mac. Neither is a production number.
- Prices and rate limits (1,200 req/min at the time of writing) are early-access figures and
  can change; the run records the served model id so a later alias move is diffable.

## Limitations

- Golden dataset: human-verified (80/80). The held-out set for the Jev criteria is AI-drafted.
- Judge = same 4B model as the feature; a stronger, separate judge would be better.
- No GitHub repository connected yet, so the Actions workflow has not executed remotely; GitHub
  Actions inference would need an API key or a reachable model endpoint as a secret.
- Slack delivery not exercised live.
- Docker image not built here (disk).
