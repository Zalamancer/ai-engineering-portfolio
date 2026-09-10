# AWS cost plan — project 3 only

**Status (2026-09-10): deployed.** Ihsan confirmed "$30 per month" (asked to stay under $20). Created so far:
- AWS Budget `portfolio-20-monthly` — $20/month, e-mail alerts at 40 % / 75 % / 100 % actual and 100 % forecast.
- Lightsail instance `agentops-1` (small_3_0, Ubuntu 22.04, us-east-1a, $12/month) with static IP `agentops-1-ip`
  (free while attached), firewall **SSH only**; API/console reachable only through an SSH tunnel.
- Services api / worker / console / testtarget under systemd (`deploy/server_setup.sh`); measured on the server:
  565 MB used of 1910 MB with everything idle.
- Pending: Bedrock (account verification by AWS, then the `bedrock` profile on the server); CloudWatch log shipping.
Teardown: `03-agent-orchestration/scripts/aws_teardown.sh`. Backup: `scripts/aws_backup.sh` (creates the S3 bucket on first use).

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

Measured natively on the Mac (2026-09-10, idle after startup, resident memory): worker **569 MB** (holds the
embedding model), API 53 MB, console 68 MB, test target 7 MB, plus ~30 MB per `uv run` wrapper → **≈ 790 MB total**.
Under load the worker grows by a few hundred MB. With Ubuntu's own ~150 MB this fits the **2 GB `small_3_0` plan
with ~1 GB headroom**, so no upgrade is planned. (Docker Desktop's disk filled up during the image build, so the
container measurement was replaced by the native one; on the server the services run under systemd via `uv`, which
also avoids Docker's overhead on a 2 GB box.)

## Controls before anything is created

1. AWS Budget `portfolio-20-monthly` at $20/month, alerts 40/75/100 % actual + 100 % forecast, e-mailed to Ihsan — **created 2026-09-10**.
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
