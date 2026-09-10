# API + UI image. The LLM is NOT in this image: it runs on the host (mlx_lm on Apple silicon)
# or any OpenAI-compatible endpoint given by RAG_LLM_BASE_URL. Embeddings/reranker run inside
# the container on CPU (models are downloaded on first start unless mounted from a cache).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY hybrid_rag ./hybrid_rag
COPY scripts ./scripts
COPY eval/questions.json ./eval/questions.json
ENV PATH="/app/.venv/bin:$PATH" RAG_API_HOST=0.0.0.0
EXPOSE 8000 8501
CMD ["uvicorn", "hybrid_rag.api:app", "--host", "0.0.0.0", "--port", "8000"]
