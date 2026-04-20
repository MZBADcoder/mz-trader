"""Celery tasks for bars refresh and finalization."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from application.container import Container
from settings import get_settings
from worker.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(name="worker.tasks.bar_refresh.run_current_day_bars_refresh")
def run_current_day_bars_refresh() -> dict[str, Any]:
    return asyncio.run(_run_current_day_bars_refresh())


@celery_app.task(name="worker.tasks.bar_refresh.run_post_close_bars_finalizer")
def run_post_close_bars_finalizer() -> dict[str, Any]:
    return asyncio.run(_run_post_close_bars_finalizer())


@celery_app.task(name="worker.tasks.bar_refresh.run_ticker_bars_bootstrap")
def run_ticker_bars_bootstrap() -> dict[str, Any]:
    return asyncio.run(_run_ticker_bars_bootstrap())


@celery_app.task(name="worker.tasks.bar_refresh.run_historical_bars_gap_reconciliation")
def run_historical_bars_gap_reconciliation() -> dict[str, Any]:
    return asyncio.run(_run_historical_bars_gap_reconciliation())


@celery_app.task(name="worker.tasks.bar_refresh.run_bars_retention_cleanup")
def run_bars_retention_cleanup() -> dict[str, Any]:
    return asyncio.run(_run_bars_retention_cleanup())


async def _run_current_day_bars_refresh() -> dict[str, Any]:
    settings = get_settings()
    container = Container(settings)
    try:
        result = await container.get_run_current_day_bars_refresh_service().execute()
    finally:
        await container.shutdown()

    payload = _to_refresh_payload(result)
    logger.info("current-day bars refresh completed", extra=payload)
    return payload


async def _run_post_close_bars_finalizer() -> dict[str, Any]:
    settings = get_settings()
    container = Container(settings)
    try:
        result = await container.get_run_post_close_bars_finalizer_service().execute()
    finally:
        await container.shutdown()

    payload = _to_refresh_payload(result)
    logger.info("post-close bars finalizer completed", extra=payload)
    return payload


async def _run_ticker_bars_bootstrap() -> dict[str, Any]:
    settings = get_settings()
    container = Container(settings)
    try:
        result = await container.get_run_ticker_bars_bootstrap_service().execute()
    finally:
        await container.shutdown()

    payload = _to_refresh_payload(result)
    logger.info("ticker bars bootstrap completed", extra=payload)
    return payload


async def _run_historical_bars_gap_reconciliation() -> dict[str, Any]:
    settings = get_settings()
    container = Container(settings)
    try:
        result = await container.get_run_historical_bars_gap_reconciliation_service().execute()
    finally:
        await container.shutdown()

    payload = {
        "status": result.status,
        "total_tickers": result.total_tickers,
        "processed_tickers": result.processed_tickers,
        "failed_tickers": result.failed_tickers or [],
        "skip_reason": result.skip_reason,
    }
    logger.info("historical bars gap reconciliation completed", extra=payload)
    return payload


async def _run_bars_retention_cleanup() -> dict[str, Any]:
    settings = get_settings()
    container = Container(settings)
    try:
        result = await container.get_run_bars_retention_cleanup_service().execute()
    finally:
        await container.shutdown()

    payload = {
        "status": result.status,
        "deleted_1m_rows": result.deleted_1m_rows,
        "deleted_1d_rows": result.deleted_1d_rows,
        "skip_reason": result.skip_reason,
    }
    logger.info("bars retention cleanup completed", extra=payload)
    return payload


def _to_refresh_payload(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "total_tickers": result.total_tickers,
        "refreshed_tickers": result.refreshed_tickers,
        "failed_tickers": result.failed_tickers,
        "skip_reason": result.skip_reason,
    }
