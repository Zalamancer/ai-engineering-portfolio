# Interview notes and resume bullets

Plain-language walkthroughs of the three projects, the measured results, the failures, and the
trade-offs, so the work can be discussed honestly. Every number below is in `EVIDENCE_LEDGER.md`.

## Resume bullets (only claims backed by measurements)

- Built a hybrid-search RAG service (BM25 + dense embeddings fused with Reciprocal Rank Fusion, cross-encoder
  reranking, grounded generation with claim-level citation verification and explicit abstention) over 198 public
  technical documents in four formats; evaluated 18 retrieval configurations and 6 end-to-end configurations on a
  75-question suite, raising retrieval hit@5 from 58 % (dense-only baseline) to 82 % (hybrid) and answer correctness
  from 75 % to 81 %, and documenting that plain BM25 (92 %) beat hybrid on the (AI-drafted, human-verified) question set.
- Built an LLM regression gate for a support-email classifier: versioned prompts, an 80-case human-verified golden
  dataset with deliberate edge cases, multi-dimensional scoring, baseline diffing with policy thresholds *and* exact
  McNemar / Wilson statistics, HTML diff reports, drift detection, Slack payloads and a GitHub Actions PR gate;
  demonstrated it blocking an intentionally broken prompt (−61 pp, exit code 2) while passing a benign change (−1.2 pp,
  p = 1.0).
- Built a supervisor / specialist / reviewer multi-agent system on LangGraph with a schema-validated tool registry,
  sandboxed code execution, human approval pauses/resumes, budgets enforced in code (steps, calls, tokens, time, cost
  ledger), durable state and long-term memory outside the process, and crash recovery that never repeats external
  writes (verified by tests and live runs); deployed on AWS Lightsail with Bedrock, CloudWatch, S3 and a budget cap,
  where a full run costs ~$0.003.

Do not claim: customer impact, production traffic, cost savings, or that any model judgment is a human judgment.

## Project 1 — Hybrid RAG (say it in 60 seconds)

"I built a question-answering service over a technical documentation corpus. Documents in markdown, text, HTML and
PDF are normalised into one format so section and page metadata are exact. I index every chunk twice — a vector index
and a keyword index — fuse the two rankings with RRF, rerank the top 20 with a cross-encoder, and generate an answer
that must cite passages by number. Then I verify each citation: every sentence is a claim, and a judge checks whether
the cited passage actually supports it. If retrieval confidence is low the system says what it found and where to look
instead of guessing."

The result I lead with: hybrid beat the dense-only baseline by 24 points of retrieval recall and 6 points of answer
correctness. The result I volunteer next: keyword search alone beat hybrid on my question set (92 % vs 81 %), and I
think that is because I drafted the questions from the text, so they reuse exact identifiers — which is exactly what
BM25 rewards. I then reviewed all 75 questions myself (no answers needed changing), but the phrasing bias remains: questions written by real users, not from the text, are the test that settles it.

Failures I can describe: the near-duplicate filter dropped a "response headers" passage because FastAPI's docs are
templated; the PDF extractor displaced RFC "MUST/SHOULD" keywords; the 4B model sometimes leaves the first sentence
uncited so coverage penalises style; ambiguity handling only worked half the time.

Trade-offs: local 4B model (free, weak) instead of GPT-4o; the judge is the same model as the generator; small corpus.

## Project 2 — Regression gate (60 seconds)

"Teams change prompts blind. I built a CI gate: prompts are versioned YAML, a golden dataset of 80 support emails has
human-verified labels, every run scores category accuracy, JSON validity, summary quality from a judge, latency and
tokens, and compares against a saved baseline case by case. A drop over 3 points warns, over 8 blocks the merge. I
also report the exact p-value and confidence intervals because with 80 cases a 3-point change is usually noise — the
threshold is a policy, not a significance test."

The demo: v1 baseline 85 % → v3-bad 24 % (critical, blocked, 50 regressions) → v2/v4 within noise (pass). The
interesting detail: v2's "improvement" actually pushed short billing emails to "general"; the per-category table shows
billing −25 pp while others were flat — the gate found a real behavioural change hidden inside a small overall delta.

Dataset story: I drafted the cases, then reviewed all 80 myself and changed 6 labels. The verdict on v2 moved from
WARN to PASS after those corrections — a concrete example of why label quality bounds evaluation quality.

Trade-off: the judge is the local model; live Slack delivery and Actions inference need a model key.

## Project 3 — Agent orchestration (60 seconds)

"A supervisor decomposes a request into a dependency graph of tasks, research/analysis/writing specialists execute
them with registered tools that validate inputs and outputs, and a reviewer checks every output — programmatic
checks first (citations must be things a tool actually returned, numbers must appear in a tool result, required
actions must have happened), then a model verdict. Sensitive actions pause the run for a human; the run state is
checkpointed in SQLite after every node, so a killed worker resumes from the checkpoint, and side effects are idempotent
so an external write is never repeated. Every budget — steps, model calls, tool calls, tokens, time, cost — is enforced
in code and exhaustion is an explicit state."

Evidence: 11 tests with a scripted model cover approval pause/resume, budget exhaustion, crash recovery with exactly one
external write, bounded reviewer corrections. One live run completed end to end with the local model: research →
SQL analysis → report posted once to a local webhook after approval.

Failures I found in live runs (and fixed): the reviewer rejected correct citations inherited from an earlier task; the
SQL tool did not tell the model the schema; the approved action was re-asked with different arguments; wall-clock budget
charged idle time; and the writer invented "12 sections / 8 HTTPS" when SQL said 135 / 256 — the reviewer missed it,
so I added a numeric-grounding check. The supervisor's own confidence (0.95) predicted nothing about execution quality.

Cloud: deployed on a $12/month Lightsail box with Bedrock Nova Lite; a full run costs about a third of a cent and takes
~50 s; budget alert, SSH-only access, CloudWatch logs, S3 backups, one-command teardown.

Trade-offs: SQLite instead of Postgres/Redis (same guarantees tested, one file), no OpenTelemetry (structured event
table instead), no replay UI, single instance with no high availability.

## Questions to expect

- *Why not just use a vector database?* — Show the 58 % vs 82 % hit@5 and explain identifiers like `--proxy-headers`.
- *How do you know the judge is right?* — I don't fully; judge = generator here. The fix is a human-calibrated judge.
- *Is 3 % a significant regression?* — No; at n = 80 the 95 % interval is ±7 pp. It is a policy trigger for review.
- *What happens if the worker dies mid-run?* — Checkpoint resume plus idempotency keys; there is a test that kills it
  right after an external write and checks the target received exactly one.
