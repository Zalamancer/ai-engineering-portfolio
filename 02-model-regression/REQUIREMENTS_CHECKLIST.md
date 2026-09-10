# Requirements checklist — guide project #1 (pp. 3–5)

| # | Guide requirement | Status | Where / evidence | Adaptation / limitation |
|---|---|---|---|---|
| 1.1 | Simple LLM feature: email → category (billing/technical/account/general) + one-sentence summary; prompt as configurable parameter | ✅ | `regress/feature.py` (`Classifier.classify(email, PromptConfig)`) | — |
| 1.2 | Prompts as versioned YAML: version id, timestamp, system prompt, few-shot | ✅ | `prompts/v1.yaml`, `v2.yaml`, `v3-bad.yaml` | — |
| 1.3 | PromptConfig dataclass, Pydantic-typed structured output | ✅ | `PromptConfig`, `Classification` (Pydantic) | — |
| 2.1 | 50–100 hand-curated test cases, human-verified, NOT LLM-generated | 🟡 | `data/golden/golden.json` 80 cases; review UI `scripts/review_ui.py`; `n_verified` recorded per run | **Cases are AI-drafted and labelled `ai_generated`; human verification pending.** Not claimed as satisfying the requirement |
| 2.2 | Edge cases: ambiguous, extremely short, typos, mixed languages, sarcastic; `expected_difficulty` | ✅ | tags `mixed`(12) `short`(4) `typos`(2) `mixed-language`(4) `sarcasm`(4) `angry`(1); difficulty easy/medium/hard | — |
| 2.3 | Versioned JSON with stable id, input, expected output, difficulty, notes | ✅ | dataset `version` + content `fingerprint` stored on every run | — |
| 3.1 | Test runner over the whole dataset, async batching | ✅ | `regress/runner.py` (`asyncio` + semaphore) | local server is effectively serial |
| 3.2 | Multi-dimensional scoring: category match, summary LLM-judge 1–5, latency, tokens; stored per case | ✅ | `regress/scoring.py`, `case_results` table | judge = local model |
| 3.3 | Comparison: pass-rate delta, per-category delta, regressions (pass→fail), improvements (fail→pass) | ✅ | `regress/compare.py` | — |
| 3.4 | "Statistical significance": warn > 3 %, critical > 8 %, configurable | ✅ (renamed) | policy thresholds `REG_WARN_DELTA`/`REG_CRITICAL_DELTA` **plus** exact McNemar p-value and Wilson CIs | Prompt requires not calling thresholds significance |
| 4.1 | HTML diff report: metadata, scorecard vs baseline, side-by-side regressed cases, trend chart over last N runs | ✅ | `regress/report.py` → `reports/<run_id>.html` | inline SVG chart |
| 4.2 | Slack incoming webhook: status, headline numbers, link to report | 🟡 | `regress/alerts.py` (Block Kit), outbox | **Live delivery pending authorisation**; payload verified locally + in tests |
| 4.3 | Drift detection: 7-run moving average below threshold → slow-drift warning | ✅ | `regress/drift.py` | — |
| 5.1 | GitHub Action on PRs touching /prompts: run eval, report, PR comment, block merge on critical | 🟡 | `.github/workflows/regression.yml` | Repo connected (Zalamancer/ai-engineering-portfolio); workflow runs tests on PRs, eval step needs model-access secrets |
| 5.2 | Dockerfile with env vars for API key, webhook, thresholds | 🟡 | `Dockerfile` | Not built (disk) |
| 5.3 | README as internal docs: summary, setup, adding cases, thresholds, architecture rationale | ✅ | `README.md` | — |
| 6.1 | Loom walkthrough | ⚪ | — | human task |
| 6.2 | Blog/README section on a design decision | ✅ | README "Architecture decisions" (drift vs per-run) | — |
| + | Demonstrate an intentionally bad change failing the gate | ✅/pending run | `prompts/v3-bad.yaml`, `scripts/demo_runs.sh`, exit code 2 | measured result recorded in EVIDENCE_LEDGER when the run completes |
