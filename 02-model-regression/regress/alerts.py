"""Slack alerting (guide Phase 4.2). Messages are BUILT always and SENT only when a webhook URL is
configured and --send is given. Otherwise the payload is written to alerts/outbox/ and delivery is
marked pending — nothing leaves this machine without explicit authorisation."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

EMOJI = {"pass": "✅", "warn": "⚠️", "critical": "🚨"}


def build_slack_message(cand_meta: dict, comparison: dict | None, drift: dict | None, report_url: str | None) -> dict:
    v = comparison["verdict"] if comparison else "pass"
    if comparison:
        head = (f"{EMOJI[v]} *{v.upper()}* — prompt `{cand_meta['prompt_version']}` vs baseline `{comparison['baseline_run_id']}`: "
                f"{len(comparison['regressions'])} regressions, {len(comparison['improvements'])} improvements, "
                f"pass rate {100 * comparison['baseline_pass_rate']:.0f}% → {100 * comparison['candidate_pass_rate']:.0f}%")
        stats = comparison["stats"]
        detail = (f"category accuracy Δ {100 * (comparison['category_accuracy_delta'] or 0):+.1f} pp · n={stats['n']} · "
                  f"exact p={stats['mcnemar_exact_p_value']} · 95% CI candidate {stats['candidate_pass_rate_wilson95']}")
    else:
        head = f"{EMOJI['pass']} eval run `{cand_meta['run_id']}` — pass rate {100 * (cand_meta['pass_rate'] or 0):.0f}% (no baseline to compare)"
        detail = f"n={cand_meta['n_cases']} · dataset {cand_meta['dataset_version']} ({cand_meta['dataset_label']})"
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": head}},
              {"type": "context", "elements": [{"type": "mrkdwn", "text": detail}]}]
    if comparison and comparison["regressions"]:
        lines = "\n".join(f"• `{r['case_id']}` ({r['expected_category']}, {r['difficulty']}): {r['reason']}" for r in comparison["regressions"][:5])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Regressed cases*\n{lines}"}})
    if drift and drift.get("drift"):
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"🐢 *Slow drift*: {drift['reason']}"}})
    if report_url:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"<{report_url}|Open the full HTML diff report>"}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                   f"model `{cand_meta['model']}` · judge `{cand_meta.get('judge_model')}` · dataset {cand_meta['dataset_label']}"}]})
    return {"text": head, "blocks": blocks}


def deliver(payload: dict, webhook_url: str, send: bool, outbox: Path) -> dict:
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    if not send:
        return {"delivered": False, "status": "pending: --send not given", "saved_to": str(path)}
    if not webhook_url:
        return {"delivered": False, "status": "pending: REG_SLACK_WEBHOOK_URL not configured", "saved_to": str(path)}
    r = httpx.post(webhook_url, json=payload, timeout=10)
    return {"delivered": r.status_code == 200, "status": f"slack responded {r.status_code}", "saved_to": str(path)}
