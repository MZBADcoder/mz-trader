"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend runtime configuration."""

    app_name: str = "trader-refactor-backend"
    app_env: str = "dev"
    app_secret_key: str = "replace-with-strong-random-secret"
    auth_access_token_ttl_seconds: int = 86_400
    auth_jwt_algorithm: str = "HS256"
    password_hash_iterations: int = 600_000
    password_hash_salt_bytes: int = 16

    massive_api_key: str = ""
    massive_stock_plan: str = "developer"
    massive_base_url: str = "https://api.massive.com"
    massive_timeout_seconds: float = 10.0

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trader_refactor"
    redis_url: str = "redis://localhost:6379/0"

    log_level: str = "INFO"
    log_dir: Path = Field(default=Path("var/log"))
    log_file_name: str = "application.log"
    log_backup_count: int = 14
    log_to_stdout: bool = True
    request_id_header: str = "X-Request-ID"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def app_log_path(self) -> Path:
        """Resolve the configured application log file path."""
        return self.log_dir / self.log_file_name


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for the process lifetime."""
    return Settings()
