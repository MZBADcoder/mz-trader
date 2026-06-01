"""CORS middleware tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import create_app
from settings import Settings


def _build_client(tmp_path: Path, *, origins: str) -> TestClient:
    settings = Settings(
        app_env="test",
        app_secret_key="test-secret",
        cors_allowed_origins=origins,
        log_dir=tmp_path,
        log_file_name="test.log",
        log_to_stdout=False,
    )
    return TestClient(create_app(settings))


def test_cors_preflight_allows_configured_frontend_origin(tmp_path: Path) -> None:
    client = _build_client(tmp_path, origins="http://localhost:5173")

    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_allow_unconfigured_origin(tmp_path: Path) -> None:
    client = _build_client(tmp_path, origins="http://localhost:5173")

    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://malicious.local"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
