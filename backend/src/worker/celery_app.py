"""Celery application wiring."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from settings import get_settings


settings = get_settings()

celery_app = Celery(
    "trader-refactor-backend",
    broker=settings.celery_broker_url,
    backend=settings.resolved_celery_result_backend,
    include=["worker.tasks.snapshot_coordinator", "worker.tasks.bar_refresh"],
)

celery_app.conf.update(
    timezone="America/New_York",
    enable_utc=True,
    task_ignore_result=True,
    beat_schedule={
        "snapshot-coordinator-refresh": {
            "task": "worker.tasks.snapshot_coordinator.run_snapshot_coordinator_refresh",
            "schedule": settings.resolved_market_data_snapshot_refresh_interval_seconds,
        },
        "current-day-bars-refresh": {
            "task": "worker.tasks.bar_refresh.run_current_day_bars_refresh",
            "schedule": settings.resolved_market_data_bars_current_day_refresh_interval_seconds,
        },
        "post-close-bars-finalizer": {
            "task": "worker.tasks.bar_refresh.run_post_close_bars_finalizer",
            "schedule": settings.resolved_market_data_bars_post_close_finalizer_interval_seconds,
        },
        "ticker-bars-bootstrap": {
            "task": "worker.tasks.bar_refresh.run_ticker_bars_bootstrap",
            "schedule": settings.resolved_market_data_bars_bootstrap_interval_seconds,
        },
        "historical-bars-gap-reconciliation": {
            "task": "worker.tasks.bar_refresh.run_historical_bars_gap_reconciliation",
            "schedule": crontab(
                minute=settings.market_data_bars_gap_reconcile_minute_et,
                hour=settings.market_data_bars_gap_reconcile_hour_et,
            ),
        },
        "bars-retention-cleanup": {
            "task": "worker.tasks.bar_refresh.run_bars_retention_cleanup",
            "schedule": crontab(
                minute=settings.market_data_bars_retention_cleanup_minute_et,
                hour=settings.market_data_bars_retention_cleanup_hour_et,
            ),
        },
    },
)
