"""FastAPI application bootstrap."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_exception_handlers
from api.middleware.request_context import RequestContextMiddleware
from api.routers import router as api_router
from application.container import Container
from bootstrap.logging import configure_logging
from infrastructure.external import MassiveSnapshotClient
from settings import Settings, get_settings


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log application lifecycle events once logging is configured."""
    settings: Settings = app.state.settings
    logger.info(
        "application startup",
        extra={"app_env": settings.app_env, "log_path": str(settings.app_log_path)},
    )
    startup_task = asyncio.create_task(_run_startup_reconciliation(app.state.container))
    app.state.startup_reconciliation_task = startup_task
    yield
    await _await_background_task(app.state.startup_reconciliation_task)
    await app.state.container.shutdown()
    logger.info("application shutdown", extra={"app_env": settings.app_env})


def create_app(
    settings: Settings | None = None,
    *,
    snapshot_client: MassiveSnapshotClient | None = None,
    now_provider: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Create a FastAPI app wired with the logging scaffold."""
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.container = Container(
        app_settings,
        snapshot_client=snapshot_client,
        now_provider=now_provider,
    )
    _add_cors_middleware(app, app_settings)
    app.add_middleware(
        RequestContextMiddleware,
        request_id_header=app_settings.request_id_header,
    )
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


def _add_cors_middleware(app: FastAPI, settings: Settings) -> None:
    allowed_origins = settings.resolved_cors_allowed_origins
    if not allowed_origins:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", settings.request_id_header],
        expose_headers=[settings.request_id_header],
    )


async def _run_startup_reconciliation(container: Container) -> None:
    try:
        result = await container.get_run_bars_startup_reconciliation_service().execute()
    except Exception:
        logger.exception("startup bars reconciliation failed")
        return

    logger.info(
        "startup bars reconciliation completed",
        extra={
            "status": result.status,
            "total_tickers": result.total_tickers,
            "processed_tickers": result.processed_tickers,
            "failed_tickers": result.failed_tickers or [],
            "skip_reason": result.skip_reason,
        },
    )


async def _await_background_task(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    if task.done():
        try:
            await task
        except Exception:
            logger.exception("background task completed with error")
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("background task completed with error")


app = create_app()
