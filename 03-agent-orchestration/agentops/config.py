from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AO_", env_file=ROOT / ".env", extra="ignore")

    # --- storage (all outside the agent process) ---------------------------------
    data_dir: Path = ROOT / "data"
    db_path: Path = ROOT / "data" / "agentops.db"            # runs, tasks, events, approvals, ledger, memory, side effects
    checkpoint_db_path: Path = ROOT / "data" / "checkpoints.db"  # LangGraph state checkpoints
    chroma_dir: Path = ROOT / "data" / "chroma"              # long-term semantic memory vectors
    workspace_dir: Path = ROOT / "data" / "workspaces"       # per-run file sandbox for file tools

    # --- models ----------------------------------------------------------------------
    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_api_key: str = "local-no-key"
    llm_model: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    reviewer_model: str = ""                                  # empty = same model
    llm_timeout_s: float = 180.0
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # estimated price per 1k tokens (USD) used by the usage ledger; 0 for the local model
    price_in_per_1k: float = 0.0
    price_out_per_1k: float = 0.0
    reserve_tokens_per_call: int = 2500                       # reserved before each call, reconciled after

    # --- budgets enforced in code (per run) --------------------------------------------
    max_steps: int = 40                                       # graph node executions
    max_llm_calls: int = 30
    max_tool_calls: int = 25
    max_tokens_total: int = 60_000
    max_wall_seconds: int = 1800                              # active processing time (a slow shared local model needs headroom)
    max_retries_per_task: int = 2
    max_review_rounds: int = 2                                # bounded reviewer corrections
    max_tool_iterations_per_task: int = 6
    max_concurrency: int = 2                                  # parallel specialists
    max_cost_usd: float = 0.50
    app_allowance_usd: float = 5.00                           # whole-app allowance; model calls disabled when exhausted

    # --- human-in-the-loop -----------------------------------------------------------------
    plan_confidence_threshold: float = 0.6                    # below → approve_plan
    review_score_threshold: int = 3                           # reviewer score ≤ this after max rounds → take_over
    sensitive_tools: tuple[str, ...] = ("http_post", "write_file")  # → approve_action before execution
    always_approve_plan: bool = False                         # user explicitly requests human review

    # --- tools ---------------------------------------------------------------------------------
    web_search_live: bool = False                             # False = fixture/offline search only
    fetch_allowlist: tuple[str, ...] = ("https://", "http://127.0.0.1")
    http_post_allowlist: tuple[str, ...] = ("http://127.0.0.1:8099",)   # local test target only
    test_target_port: int = 8099
    docs_corpus_path: Path = ROOT.parent / "01-hybrid-rag" / "data" / "processed" / "docs.jsonl"
    python_exec_timeout_s: int = 10
    python_exec_mem_mb: int = 512

    # --- service -------------------------------------------------------------------------------
    api_port: int = 8010
    worker_poll_s: float = 1.0
    lease_seconds: int = 60


settings = Settings()
