"""Logging bootstrap tests."""

from __future__ import annotations

import json
import logging

from bootstrap.logging import JsonLogFormatter, configure_logging
from bootstrap.request_context import RequestLogContext, reset_request_context, set_request_context
from settings import Settings


def test_json_log_formatter_includes_request_context() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="tests.logging",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    token = set_request_context(
        RequestLogContext(
            request_id="req-12345678",
            method="GET",
            path="/health",
        )
    )
    try:
        payload = json.loads(formatter.format(record))
    finally:
        reset_request_context(token)

    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-12345678"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"


def test_configure_logging_writes_json_lines_to_file(tmp_path) -> None:
    settings = Settings(
        log_dir=tmp_path,
        log_file_name="backend.log",
        log_to_stdout=False,
    )
    configure_logging(settings)

    logger = logging.getLogger("tests.logging.file")
    logger.info("file logging works", extra={"upstream_service": "massive"})

    for handler in logging.getLogger().handlers:
        handler.flush()

    log_path = tmp_path / "backend.log"
    assert log_path.exists()

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["message"] == "file logging works"
    assert payload["upstream_service"] == "massive"


def test_configure_logging_can_write_to_explicit_file_name(tmp_path) -> None:
    settings = Settings(
        log_dir=tmp_path,
        log_file_name="backend.log",
        log_to_stdout=False,
    )
    configure_logging(settings, log_file_name="celery-worker.log")

    logger = logging.getLogger("tests.logging.celery")
    logger.info("celery file logging works")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert not (tmp_path / "backend.log").exists()
    log_path = tmp_path / "celery-worker.log"
    assert log_path.exists()

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["message"] == "celery file logging works"
