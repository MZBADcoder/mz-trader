"""Centralized logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from seqlog.feature_flags import FeatureFlag, configure_feature
from seqlog.structured_logging import SeqLogHandler

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
_INTERNAL_RECORD_FIELDS = frozenset({"log_props"})
_SEQ_RECORD_PROPERTIES_ATTR = "_seq_log_properties"


def _collect_context_fields(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    context = get_request_context()

    for field in _CONTEXT_FIELDS:
        value = getattr(record, field, None)
        if value is None:
            value = getattr(context, field)
        if value is not None:
            payload[field] = value

    return payload


def _collect_extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    for key, value in record.__dict__.items():
        if key in _BASE_RECORD_FIELDS or key in _CONTEXT_FIELDS or key in _INTERNAL_RECORD_FIELDS:
            continue
        if key.startswith("_"):
            continue
        if value is not None:
            payload[key] = value

    return payload


class JsonLogFormatter(logging.Formatter):
    """Render log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        payload.update(_collect_context_fields(record))
        payload.update(_collect_extra_fields(record))

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)


class ContextSeqLogHandler(SeqLogHandler):
    """Send standard logging records to Seq with project context fields."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setFormatter(logging.Formatter())

    def emit(self, record: logging.LogRecord) -> None:
        setattr(
            record,
            _SEQ_RECORD_PROPERTIES_ATTR,
            {
                **_collect_context_fields(record),
                **_collect_extra_fields(record),
            },
        )
        super().emit(record)

    def _build_event_data_ingest(self, record: logging.LogRecord) -> dict[str, Any]:
        event_data = super()._build_event_data_ingest(record)
        properties = event_data.setdefault("Properties", {})
        properties.update(getattr(record, _SEQ_RECORD_PROPERTIES_ATTR, {}))
        return event_data

    def _build_event_data_clef(self, record: logging.LogRecord) -> dict[str, Any]:
        event_data = super()._build_event_data_clef(record)
        event_data.update(getattr(record, _SEQ_RECORD_PROPERTIES_ATTR, {}))
        return event_data


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


def _build_seq_handler(settings: Settings) -> ContextSeqLogHandler | None:
    if not settings.seq_url:
        return None

    configure_feature(FeatureFlag.IGNORE_SEQ_SUBMISSION_ERRORS, settings.seq_ignore_submission_errors)
    handler = ContextSeqLogHandler(
        server_url=settings.seq_url,
        api_key=settings.seq_api_key or None,
        batch_size=settings.seq_batch_size,
        auto_flush_timeout=settings.seq_auto_flush_timeout_seconds,
    )
    return handler


def _close_handlers(handlers: list[logging.Handler]) -> None:
    for handler in handlers:
        handler.close()


def configure_logging(
    settings: Settings,
    *,
    log_file_name: str | None = None,
    log_level: int | str | None = None,
) -> None:
    """Configure root logging once per process configuration load."""
    log_path = settings.log_dir / (log_file_name or settings.log_file_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    existing_handlers = list(root_logger.handlers)
    root_logger.handlers.clear()
    _close_handlers(existing_handlers)

    root_logger.setLevel(log_level if log_level is not None else settings.log_level.upper())
    root_logger.addHandler(_build_file_handler(log_path, settings.log_backup_count))

    seq_handler = _build_seq_handler(settings)
    if seq_handler is not None:
        root_logger.addHandler(seq_handler)

    if settings.log_to_stdout:
        root_logger.addHandler(_build_stream_handler())

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy", "sqlalchemy.engine"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    logging.captureWarnings(True)
