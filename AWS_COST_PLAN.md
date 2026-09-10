# AWS cost plan — project 3 only

**Status (2026-09-10): account connected (IAM user `agentops-deploy`, region us-east-1), prices verified via the
AWS CLI, nothing provisioned yet.** Deployment waits for Ihsan's confirmation of the budget reading and of this plan.

## Budget interpretation (to confirm)

- Working assumption: **at most $30 per month**, all-in. Planning target **$20–22/month**.
- If it was meant as $30 *total* for the whole build, this plan still fits for roughly one month, then must be torn down.
- AWS Budgets alerts are delayed (hours) and are **not a hard cap**. The hard controls are in the application
  (usage ledger, model calls refused past the allowance, per-run budgets) and the teardown command.

## Verified prices (CLI, us-east-1, 2026-09-10)

| Item | Choice | Verified price | Planned monthly |
|---|---|---|---|
| Compute | Lightsail `small_3_0` — 2 vCPU, 2 GB RAM, 60 GB SSD, 3 TB transfer | **$12.00/month** (`get-bundles`) | $12.00 |
| Compute fallback if 2 GB is too small after measurement | Lightsail `medium_3_0` — 4 GB RAM | $24.00/month | (would consume most of the budget — not silent, needs a decision) |
| Model | Amazon Bedrock **Nova Lite** on-demand | **$0.00006 / 1k input tokens, $0.00024 / 1k output tokens** (`pricing get-products`) | $0.50 for 100 demo runs (see workload) |
| Model alternative | Bedrock Claude Haiku 4.5 (inference profile) | not priced here; roughly 15–20× Nova Lite per token | ~$8–9 for 100 runs — only if quality demands it |
| Object storage | S3 standard, run artifacts + DB backups (< 1 GB) | ~$0.023/GB-month list price | < $0.10 |
| Logs / metrics | CloudWatch, 7-day retention, < 1 GB ingest | list price ~$0.50/GB ingested | < $0.50 |
| Transfer | included in Lightsail allowance (3 TB) | $0 | $0 |
| Taxes / headroom | depends on billing country | — | ~$3 |
| **Total planned** | | | **≈ $16–17/month** (target ≤ $22, cap $30) |

The $12 plan matches Ihsan's note from 2026-09-09. The instance is the whole cost story; everything else is cents.

## Workload assumptions (from the local build, EVIDENCE_LEDGER R3-DEMO)

- One full run ≈ 28 model calls, ≈ 39k input + 9k output tokens (local 4B model; a cloud model may use fewer retries).
- Demo usage assumed ≤ 100 runs/month → 4M input + 0.9M output tokens → Nova Lite ≈ $0.24 + $0.22 ≈ **$0.46**.
- Application allowance set to **$5.00/month** in code (`AO_APP_ALLOWANCE_USD`) with per-run cap $0.50: even a runaway
  cannot exceed $5 of model spend. Ledger reserves before each call and reconciles after.
- No scheduled/unattended evaluation runs on the cloud; evaluations stay local.

## Memory / CPU fit (to measure before choosing the instance)

Local container measurement: MEASUREMENT_PLACEHOLDER

## Controls before anything is created

1. AWS Budget "portfolio-30" at $30/month with alerts at 33 % / 66 % / 100 % of forecast and actual, e-mailed to Ihsan
   — created only with Ihsan's ok (it is free).
2. Demo access restricted: the API and console bound to localhost on the instance, reached through an SSH tunnel only
   (no public ports beyond SSH); concurrency 1 worker.
3. Application limits already in code: steps, LLM calls, tool calls, tokens, time, retries, review rounds, per-run cost,
   app allowance.
4. CloudWatch log retention 7 days; only the worker/API logs shipped.
5. Teardown: `03-agent-orchestration/scripts/aws_teardown.sh` (to be written with the deploy script) deletes the
   instance, static IP, S3 bucket contents + bucket, CloudWatch log groups and the budget, then lists anything left
   (`lightsail get-instances`, `s3 ls`, `logs describe-log-groups`) so no billable resource is forgotten.

## Access note

The IAM user has `PowerUserAccess` + `CloudWatchFullAccess` (broader than least privilege, because Lightsail has no
AWS-managed scoped policy and the account owner is not an IAM specialist). MFA on the root user is Ihsan's task. To
tighten later: replace PowerUserAccess with an inline policy for `lightsail:*`, `s3:*` on one bucket, `logs:*`,
`bedrock:InvokeModel*`, `budgets:*`.
