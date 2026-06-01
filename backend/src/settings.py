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
    market_data_snapshot_refresh_lock_ttl_seconds: int | None = None
    market_data_snapshot_terminal_finalizer_hour_et: int = 20
    market_data_snapshot_terminal_finalizer_minute_et: int = 30
    market_data_bars_current_day_refresh_interval_seconds: int | None = None
    market_data_bars_post_close_finalizer_hour_et: int = 17
    market_data_bars_post_close_finalizer_minute_et: int = 0
    market_data_bars_bootstrap_interval_seconds: int | None = None
    market_data_bars_gap_reconcile_max_provider_calls_per_ticker: int = 8
    market_data_bars_gap_reconcile_hour_et: int = 2
    market_data_bars_gap_reconcile_minute_et: int = 0
    market_data_bars_retention_cleanup_hour_et: int = 3
    market_data_bars_retention_cleanup_minute_et: int = 0

    log_level: str = "INFO"
    log_dir: Path = Field(default=Path("var/log"))
    log_file_name: str = "application.log"
    celery_worker_log_file_name: str = "celery-worker.log"
    celery_beat_log_file_name: str = "celery-beat.log"
    celery_log_file_name: str = "celery.log"
    log_backup_count: int = 14
    log_to_stdout: bool = True
    request_id_header: str = "X-Request-ID"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_credentials: bool = True

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
    def resolved_cors_allowed_origins(self) -> list[str]:
        """Return configured CORS origins as browser Origin header values."""
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

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
        if self.market_data_snapshot_refresh_lock_ttl_seconds is not None:
            return max(self.market_data_snapshot_refresh_lock_ttl_seconds, 60)
        return max(ceil(self.resolved_market_data_snapshot_refresh_interval_seconds * 2.5), 300)

    @property
    def resolved_market_data_bars_current_day_refresh_interval_seconds(self) -> int:
        """Return the effective current-day bars refresh interval."""
        if self.market_data_bars_current_day_refresh_interval_seconds is not None:
            return self.market_data_bars_current_day_refresh_interval_seconds
        return 60

    @property
    def resolved_market_data_bars_bootstrap_interval_seconds(self) -> int:
        """Return the effective cadence for pending ticker bootstrap scans."""
        if self.market_data_bars_bootstrap_interval_seconds is not None:
            return self.market_data_bars_bootstrap_interval_seconds
        return 60

    @property
    def resolved_celery_result_backend(self) -> str:
        """Return the configured Celery result backend."""
        return self.celery_result_backend or self.celery_broker_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for the process lifetime."""
    return Settings()
