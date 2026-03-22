"""JWT service tests."""

from __future__ import annotations

from domain.exceptions import AuthTokenExpiredError, AuthTokenInvalidError
from infrastructure.external.jwt_service import JwtService


def test_jwt_service_issues_expected_claims() -> None:
    service = JwtService(secret_key="secret", expires_in_seconds=3600)

    token = service.issue_access_token(user_id="user-1", email="user@example.com", now=100)
    payload = service.decode_access_token(token, now=101)

    assert payload["sub"] == "user-1"
    assert payload["email"] == "user@example.com"
    assert payload["iat"] == 100
    assert payload["exp"] == 3700


def test_jwt_service_rejects_tampered_token() -> None:
    service = JwtService(secret_key="secret", expires_in_seconds=3600)
    token = service.issue_access_token(user_id="user-1", email="user@example.com", now=100)
    header, payload, signature = token.split(".")
    tampered = ".".join((header, payload + "x", signature))

    try:
        service.decode_access_token(tampered, now=101)
    except AuthTokenInvalidError:
        pass
    else:
        raise AssertionError("Expected AuthTokenInvalidError")


def test_jwt_service_rejects_expired_token() -> None:
    service = JwtService(secret_key="secret", expires_in_seconds=1)
    token = service.issue_access_token(user_id="user-1", email="user@example.com", now=100)

    try:
        service.decode_access_token(token, now=101)
    except AuthTokenExpiredError:
        pass
    else:
        raise AssertionError("Expected AuthTokenExpiredError")
