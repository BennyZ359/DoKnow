"""Application configuration via pydantic-settings.

All settings are read from environment variables / .env. The values mirror
``.env.example`` at the repo root and are overridden by docker-compose for
service-to-service addresses.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General -----------------------------------------------------------
    app_name: str = "DoKnow"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"

    # --- Database (PostgreSQL + pgvector) ----------------------------------
    database_url: str = "postgresql+psycopg://doknow:doknow@localhost:5432/doknow"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # --- Redis -------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    redis_port: int = 6379

    # --- Auth --------------------------------------------------------------
    secret_key: str = Field(default="change-me-in-production", min_length=8)
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # --- LLM ---------------------------------------------------------------
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"

    # --- Document parsing --------------------------------------------------
    parser_backend: str = "docling"  # docling | mineru
    upload_dir: str = "uploads"

    # --- Agent runtime -----------------------------------------------------
    agent_heartbeat_seconds: int = 60
    agent_max_retries: int = 3
    agent_retry_backoff_seconds: float = 2.0
    agent_timeout_seconds: int = 300

    # --- CORS --------------------------------------------------------------
    # 5173: docker-compose / vite dev · 4173: vite preview
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

    @property
    def is_async_db(self) -> bool:
        return False  # sync SQLAlchemy engine (psycopg) by design


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
