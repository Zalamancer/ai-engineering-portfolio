FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY agentops ./agentops
COPY scripts ./scripts
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" AO_DATA_DIR=/app/data AO_DB_PATH=/app/data/agentops.db AO_CHECKPOINT_DB_PATH=/app/data/checkpoints.db AO_CHROMA_DIR=/app/data/chroma AO_WORKSPACE_DIR=/app/data/workspaces
VOLUME ["/app/data"]
EXPOSE 8010 8501 8099
CMD ["uvicorn", "agentops.api:app", "--host", "0.0.0.0", "--port", "8010"]
