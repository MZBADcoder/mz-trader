"""Celery application wiring."""

from __future__ import annotations

from celery import Celery

from settings import get_settings


settings = get_settings()

celery_app = Celery(
    "trader-refactor-backend",
    broker=settings.celery_broker_url,
    backend=settings.resolved_celery_result_backend,
    include=["worker.tasks.snapshot_coordinator"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    beat_schedule={
        "snapshot-coordinator-refresh": {
            "task": "worker.tasks.snapshot_coordinator.run_snapshot_coordinator_refresh",
            "schedule": settings.resolved_market_data_snapshot_refresh_interval_seconds,
        }
    },
)
