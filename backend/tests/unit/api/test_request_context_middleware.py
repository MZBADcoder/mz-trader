"""Request context middleware tests."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.request_context import RequestContextMiddleware
from bootstrap.request_context import get_request_context


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware, request_id_header="X-Request-ID")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"request_id": get_request_context().request_id or ""}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    return app


def test_request_context_middleware_propagates_valid_request_id() -> None:
    client = TestClient(_build_test_app())

    response = client.get("/health", headers={"X-Request-ID": "req-12345678"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-12345678"
    assert response.json()["request_id"] == "req-12345678"


def test_request_context_middleware_replaces_invalid_request_id() -> None:
    client = TestClient(_build_test_app())

    response = client.get("/health", headers={"X-Request-ID": "bad id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id"
    assert len(response.headers["X-Request-ID"]) == 32


def test_request_context_middleware_emits_access_log(caplog) -> None:
    client = TestClient(_build_test_app())

    with caplog.at_level(logging.INFO, logger="api.request"):
        response = client.get("/health", headers={"X-Request-ID": "req-87654321"})

    assert response.status_code == 200
    assert any(
        record.getMessage() == "request completed"
        and getattr(record, "request_id", None) == "req-87654321"
        and getattr(record, "status_code", None) == 200
        for record in caplog.records
    )
