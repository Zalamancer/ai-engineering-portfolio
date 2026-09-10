# AWS cost plan — project 3 only (draft, nothing provisioned)

**Status: no AWS resources exist. No prices have been verified by me in this session.**
This file is the template that must be completed and reviewed before anything is created.

## Budget interpretation to confirm with Ihsan

- Working assumption: **at most $30 per month**, all-in (infrastructure, model calls, storage,
  logs, transfer, taxes). Planning target **$20–22/month** to leave headroom.
- If the intent was $30 *total* for the whole build, this plan must be redone before any spend.
- Budget alerts are delayed and are **not a hard spending cap**; they cannot guarantee the
  bill stays under $30. Hard controls are in the application (usage ledger, disabled model
  calls when the allowance is exhausted) and in a teardown command.

## Candidate shape (unpriced until verified)

| Item | Candidate | To verify before deploy | Notes |
|---|---|---|---|
| Compute | Lightsail Linux, 2 GB RAM (Ihsan noted a $12/month plan on 2026-09-09) | current price in the chosen region; whether the full stack (API + worker + Redis + Postgres + Chroma) fits in 2 GB — **measure container memory locally first** | do not silently upgrade; a bigger plan eats most of the allowance |
| Object storage | S3 for run artifacts/backups | GB-month price, request pricing, lifecycle rule to expire artifacts | tiny volumes expected |
| Logs / metrics | CloudWatch, short retention (7 days) | ingestion + storage price, alarm price | keep log volume low |
| Access | IAM user/role with least privilege; MFA on the account (Ihsan) | — | never paste keys into chat |
| Model access | local/open model on the instance if it fits, else Bedrock small model | Bedrock per-token price for the chosen model and region; whether the account has Bedrock model access enabled | Claude/Claude Code subscriptions do **not** include Bedrock/API usage |
| Transfer | Lightsail includes a transfer allowance | allowance size and overage price | demo traffic only |
| Taxes | depends on billing country | add to headroom | — |

## Controls that must exist before deployment

1. Existing charges on the account accounted for inside the same $30.
2. Demo access restricted (auth or IP allow-list); concurrency limited.
3. Persistent usage ledger: reserve the estimated max cost of a model call before making it,
   reconcile actual usage after; refuse new model requests when the allowance is spent.
4. Hard limits in code: tokens, tool calls, retries, agent steps, wall-clock time.
5. AWS Budgets alert at a low threshold (e.g. $10, $20) + CloudWatch alarms; short log retention.
6. No unattended scheduled paid evaluations.
7. `teardown` command that deletes the instance, buckets (after export), alarms, and lists
   anything that could still bill (snapshots, static IPs, log groups).

## Workload assumptions (to fill with measurements from the local build)

- Requests/day for the demo, average tokens in/out per agent step, steps per run, runs per day.
- Evaluation runs: how many, how often, token cost each — **none scheduled unattended**.

Until the local project 3 exists and is measured, every number above stays blank on purpose.
