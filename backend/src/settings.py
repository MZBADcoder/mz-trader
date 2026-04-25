"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from math import ceil
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
    database_use_null_pool: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str | None = None

    market_data_delay_minutes: int = 15
    market_data_supports_stream: bool = False
    market_data_snapshot_request_limit: int = 50
    market_data_snapshot_batch_size: int = 100
    market_data_snapshot_refresh_interval_seconds: int | None = None
    market_data_snapshot_ttl_seconds: int | None = None
    market_data_bars_current_day_refresh_interval_seconds: int | None = None
    market_data_bars_post_close_finalizer_interval_seconds: int | None = None
    market_data_bars_bootstrap_interval_seconds: int | None = None
    market_data_bars_gap_reconcile_hour_et: int = 2
    market_data_bars_gap_reconcile_minute_et: int = 0
    market_data_bars_retention_cleanup_interval_seconds: int | None = None

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

    @property
    def resolved_market_data_snapshot_refresh_interval_seconds(self) -> int:
        """Return the effective snapshot refresh interval."""
        if self.market_data_snapshot_refresh_interval_seconds is not None:
            return self.market_data_snapshot_refresh_interval_seconds
        return 3 if self.market_data_delay_minutes == 0 else 10

    @property
    def resolved_market_data_snapshot_ttl_seconds(self) -> int:
        """Return the effective Redis TTL for snapshots."""
        if self.market_data_snapshot_ttl_seconds is not None:
            return self.market_data_snapshot_ttl_seconds
        return self.resolved_market_data_snapshot_refresh_interval_seconds * 5

    @property
    def resolved_market_data_snapshot_refresh_lock_ttl_seconds(self) -> int:
        """Return the Redis lock TTL for coordinator refresh single-flight."""
        return ceil(self.resolved_market_data_snapshot_refresh_interval_seconds * 2.5)

    @property
    def resolved_market_data_bars_current_day_refresh_interval_seconds(self) -> int:
        """Return the effective current-day bars refresh interval."""
        if self.market_data_bars_current_day_refresh_interval_seconds is not None:
            return self.market_data_bars_current_day_refresh_interval_seconds
        return 60

    @property
    def resolved_market_data_bars_post_close_finalizer_interval_seconds(self) -> int:
        """Return the effective cadence for the post-close finalizer task."""
        if self.market_data_bars_post_close_finalizer_interval_seconds is not None:
            return self.market_data_bars_post_close_finalizer_interval_seconds
        return 300

    @property
    def resolved_market_data_bars_bootstrap_interval_seconds(self) -> int:
        """Return the effective cadence for pending ticker bootstrap scans."""
        if self.market_data_bars_bootstrap_interval_seconds is not None:
            return self.market_data_bars_bootstrap_interval_seconds
        return 60

    @property
    def resolved_market_data_bars_retention_cleanup_interval_seconds(self) -> int:
        """Return the effective cadence for retention cleanup."""
        if self.market_data_bars_retention_cleanup_interval_seconds is not None:
            return self.market_data_bars_retention_cleanup_interval_seconds
        return 86400

    @property
    def resolved_celery_result_backend(self) -> str:
        """Return the configured Celery result backend."""
        return self.celery_result_backend or self.celery_broker_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for the process lifetime."""
    return Settings()
