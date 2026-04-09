"""Celery tasks for snapshot coordination."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from application.container import Container
from settings import get_settings
from worker.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(name="worker.tasks.snapshot_coordinator.run_snapshot_coordinator_refresh")
def run_snapshot_coordinator_refresh() -> dict[str, Any]:
    """Refresh snapshots for all distinct watchlist tickers."""
    return asyncio.run(_run_snapshot_coordinator_refresh())


async def _run_snapshot_coordinator_refresh() -> dict[str, Any]:
    settings = get_settings()
    container = Container(settings)
    try:
        result = await container.get_run_snapshot_coordinator_refresh_service().execute()
    finally:
        await container.shutdown()

    payload = {
        "total_tickers": result.total_tickers,
        "refreshed_tickers": result.refreshed_tickers,
        "failed_tickers": result.failed_tickers,
    }
    if result.failed_tickers:
        logger.warning("snapshot coordinator refresh completed with failures", extra=payload)
    else:
        logger.info("snapshot coordinator refresh completed", extra=payload)
    return payload
