FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY regress ./regress
COPY prompts ./prompts
COPY data/golden ./data/golden
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# runtime configuration via env: REG_LLM_BASE_URL, REG_LLM_API_KEY, REG_LLM_MODEL, REG_SLACK_WEBHOOK_URL, REG_WARN_DELTA, REG_CRITICAL_DELTA
VOLUME ["/app/runs", "/app/reports", "/app/alerts"]
ENTRYPOINT ["regress"]
CMD ["--help"]
