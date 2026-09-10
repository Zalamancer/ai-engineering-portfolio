# Things only you (Ihsan) can do

Newest first. Each item says why it is needed and what happens if it waits.

## Pending now

1. ~~Review the RAG question set~~ — **done 2026-09-10** (75/75 verified, no answers changed; dataset 0.2.0-reviewed).
2. ~~Review the support-email dataset~~ — **done 2026-09-09** (all 80 verified, 6 labels changed; dataset version 0.2.0-reviewed).
   One follow-up: please re-check c005 and c006 in the review screen — they were saved before the button bug was fixed.
3. ~~Free some disk space~~ — **done** (12 GB free now; Docker builds are possible again).

## Coming later (not yet)

4. **Decide on paid model access.** Everything so far uses the free local 4B model. A paid key
   (OpenAI or Anthropic) would raise quality and let GitHub Actions run the regression gate. Your
   Claude chat subscription does not include API credits. Say yes/no and a monthly cap.
5. ~~Connect GitHub~~ — **done 2026-09-09**: public repo https://github.com/Zalamancer/ai-engineering-portfolio.
   The PR gate workflow runs tests on every prompt change; the model-based eval step stays skipped (and says so)
   until you add `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` as repository secrets (needs a paid or reachable model).
6. **Slack test webhook** (optional): create an incoming webhook for a *test* channel and put the URL
   in `02-model-regression/.env` as `REG_SLACK_WEBHOOK_URL`. Until then alerts are built and saved locally, not sent.
7. **AWS** (project 3, later): confirm "$30 per month" is the right reading, sign in yourself, enable MFA,
   create least-privilege access. No resource will be created before you approve the cost sheet.
8. **Try the approval flow yourself**: start project 3's console and approve/reject a paused run
   (`uv run streamlit run agentops/ui.py` in `03-agent-orchestration/`).
