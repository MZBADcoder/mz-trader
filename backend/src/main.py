"""FastAPI application bootstrap."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.middleware.request_context import RequestContextMiddleware
from api.routers import router as api_router
from bootstrap.logging import configure_logging
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
    yield
    logger.info("application shutdown", extra={"app_env": settings.app_env})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a FastAPI app wired with the logging scaffold."""
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.add_middleware(
        RequestContextMiddleware,
        request_id_header=app_settings.request_id_header,
    )
    app.include_router(api_router)
    return app


app = create_app()
