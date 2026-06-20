"""Logging bootstrap tests."""

from __future__ import annotations

import json
import logging

import pytest
from seqlog.structured_logging import SeqLogHandler

from bootstrap.logging import ContextSeqLogHandler, JsonLogFormatter, configure_logging
from bootstrap.request_context import RequestLogContext, reset_request_context, set_request_context
from settings import Settings


@pytest.fixture(autouse=True)
def cleanup_logging_handlers():
    yield
    root_logger = logging.getLogger()
    handlers = list(root_logger.handlers)
    root_logger.handlers.clear()
    for handler in handlers:
        handler.close()


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


def test_configure_logging_adds_seq_handler_when_configured(tmp_path, monkeypatch) -> None:
    class FakeSeqHandler(logging.Handler):
        def __init__(
            self,
            server_url: str,
            api_key: str | None = None,
            batch_size: int = 10,
            auto_flush_timeout: float | None = None,
        ) -> None:
            super().__init__()
            self.server_url = server_url
            self.api_key = api_key
            self.batch_size = batch_size
            self.auto_flush_timeout = auto_flush_timeout

        def emit(self, record: logging.LogRecord) -> None:
            return None

    monkeypatch.setattr("bootstrap.logging.ContextSeqLogHandler", FakeSeqHandler)
    settings = Settings(
        log_dir=tmp_path,
        log_file_name="backend.log",
        log_to_stdout=False,
        seq_url="http://localhost:5341",
        seq_api_key="seq-key",
        seq_batch_size=25,
        seq_auto_flush_timeout_seconds=0.5,
    )

    configure_logging(settings)

    seq_handlers = [handler for handler in logging.getLogger().handlers if isinstance(handler, FakeSeqHandler)]
    assert len(seq_handlers) == 1
    assert seq_handlers[0].server_url == "http://localhost:5341"
    assert seq_handlers[0].api_key == "seq-key"
    assert seq_handlers[0].batch_size == 25
    assert seq_handlers[0].auto_flush_timeout == 0.5


def test_seq_handler_includes_request_context_and_extra_fields(monkeypatch) -> None:
    monkeypatch.setattr(SeqLogHandler, "emit", lambda self, record: None)
    handler = ContextSeqLogHandler("http://localhost:5341", batch_size=1000, auto_flush_timeout=None)
    record = logging.LogRecord(
        name="tests.logging.seq",
        level=logging.INFO,
        pathname=__file__,
        lineno=120,
        msg="seq logging works",
        args=(),
        exc_info=None,
    )
    record.ticker = "AAPL"
    record.upstream_service = "massive"

    token = set_request_context(
        RequestLogContext(
            request_id="req-seq-12345678",
            method="GET",
            path="/api/v1/market/snapshots",
        )
    )
    try:
        handler.emit(record)
        event_data = handler._build_event_data_ingest(record)
    finally:
        reset_request_context(token)
        handler.close()

    assert event_data["Properties"]["request_id"] == "req-seq-12345678"
    assert event_data["Properties"]["method"] == "GET"
    assert event_data["Properties"]["path"] == "/api/v1/market/snapshots"
    assert event_data["Properties"]["ticker"] == "AAPL"
    assert event_data["Properties"]["upstream_service"] == "massive"
