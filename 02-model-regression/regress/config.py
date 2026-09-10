from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REG_", env_file=ROOT / ".env", extra="ignore")

    # LLM under test + judge: any OpenAI-compatible endpoint (default: local mlx_lm server shared with project 1)
    llm_base_url: str = "http://127.0.0.1:8081/v1"
    llm_api_key: str = "local-no-key"
    llm_model: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    judge_model: str = ""              # empty = same as llm_model
    llm_timeout_s: float = 120.0
    concurrency: int = 2               # async batch size (local server is effectively serial)

    # thresholds — POLICY thresholds (guide p.4), not statistical significance
    warn_delta: float = 0.03           # pass-rate drop > 3 pp → warning
    critical_delta: float = 0.08       # > 8 pp → critical (blocks merge)
    summary_pass_score: int = 4        # judge score (1-5) at which a summary counts as acceptable
    drift_window: int = 7              # moving-average window (runs)
    drift_threshold: float = 0.85      # 7-run moving average of pass rate below this → slow-drift warning

    # storage
    db_path: Path = ROOT / "runs" / "runs.db"
    runs_dir: Path = ROOT / "runs"
    reports_dir: Path = ROOT / "reports"
    golden_path: Path = ROOT / "data" / "golden" / "golden.json"

    # alerting — no message is sent unless both are set AND --send is passed
    slack_webhook_url: str = ""
    report_base_url: str = ""          # e.g. GitHub Pages / artifact URL prefix for report links


settings = Settings()
