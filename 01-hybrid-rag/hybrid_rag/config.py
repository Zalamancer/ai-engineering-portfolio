"""Runtime settings. Everything is overridable through environment variables (see .env.example)."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=PROJECT_ROOT / ".env", extra="ignore")

    # --- paths -------------------------------------------------------------
    data_dir: Path = PROJECT_ROOT / "data"
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    index_dir: Path = PROJECT_ROOT / "data" / "index"

    # --- embeddings / reranker (local, free) --------------------------------
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 64
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- LLM: any OpenAI-compatible chat endpoint --------------------------
    # Default is a local mlx_lm server (scripts/serve_llm.sh). Set RAG_LLM_BASE_URL to
    # https://api.openai.com/v1 and RAG_LLM_API_KEY to use OpenAI instead.
    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_api_key: str = "local-no-key"
    llm_model: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    llm_timeout_s: float = 180.0
    llm_max_tokens: int = 600
    llm_temperature: float = 0.0

    # --- chunking -----------------------------------------------------------
    default_strategy: str = "recursive"  # fixed | recursive | semantic
    fixed_chunk_size: int = 800
    fixed_chunk_overlap: int = 120
    recursive_chunk_size: int = 900
    recursive_chunk_overlap: int = 100
    semantic_breakpoint_percentile: float = 80.0
    semantic_min_chars: int = 250
    semantic_max_chars: int = 1400
    dedup_cosine_threshold: float = 0.95

    # --- retrieval ------------------------------------------------------------
    dense_top_k: int = 10
    sparse_top_k: int = 10
    rrf_k: int = 60
    rrf_dense_weight: float = 0.7
    rrf_sparse_weight: float = 0.3
    rerank_candidates: int = 20
    final_top_k: int = 5

    # --- answer quality / abstention -------------------------------------------
    retrieval_confidence_threshold: float = 0.40  # from dev-split sweep (eval/results/threshold_sweep.json)
    verify_citations: bool = True

    # --- service -------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    def strategy_dir(self, strategy: str) -> Path:
        return self.index_dir / strategy


settings = Settings()
