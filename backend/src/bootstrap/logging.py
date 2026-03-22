"""Centralized logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from bootstrap.request_context import get_request_context
from settings import Settings


_CONTEXT_FIELDS = (
    "request_id",
    "user_id",
    "method",
    "path",
    "status_code",
    "latency_ms",
    "error_code",
    "ticker",
    "upstream_service",
)

_BASE_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)


class JsonLogFormatter(logging.Formatter):
    """Render log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        context = get_request_context()
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is None:
                value = getattr(context, field)
            if value is not None:
                payload[field] = value

        for key, value in record.__dict__.items():
            if key in _BASE_RECORD_FIELDS or key in _CONTEXT_FIELDS or key.startswith("_"):
                continue
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)


def _build_file_handler(log_path: Path, backup_count: int) -> TimedRotatingFileHandler:
    handler = TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        utc=False,
    )
    handler.setFormatter(JsonLogFormatter())
    return handler


def _build_stream_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    return handler


def _close_handlers(handlers: list[logging.Handler]) -> None:
    for handler in handlers:
        handler.close()


def configure_logging(settings: Settings) -> None:
    """Configure root logging once per process configuration load."""
    log_path = settings.app_log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    existing_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()
    _close_handlers(existing_handlers)

    root_logger.setLevel(settings.log_level.upper())
    root_logger.addHandler(_build_file_handler(log_path, settings.log_backup_count))

    if settings.log_to_stdout:
        root_logger.addHandler(_build_stream_handler())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy", "sqlalchemy.engine"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    logging.captureWarnings(True)
