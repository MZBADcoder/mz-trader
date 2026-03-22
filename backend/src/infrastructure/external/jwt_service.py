"""JWT encode/decode service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from domain.exceptions import AuthTokenExpiredError, AuthTokenInvalidError


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


class JwtService:
    """Issue and validate HMAC SHA-256 JWT access tokens."""

    def __init__(
        self,
        *,
        secret_key: str,
        expires_in_seconds: int,
        algorithm: str = "HS256",
    ) -> None:
        self._secret_key = secret_key.encode("utf-8")
        self._expires_in_seconds = expires_in_seconds
        self._algorithm = algorithm

    @property
    def expires_in_seconds(self) -> int:
        """Configured access token TTL."""
        return self._expires_in_seconds

    def issue_access_token(self, *, user_id: str, email: str, now: int | None = None) -> str:
        """Create a signed JWT."""
        if self._algorithm != "HS256":
            raise ValueError("Only HS256 is supported.")

        issued_at = now or int(time.time())
        payload = {
            "sub": user_id,
            "email": email,
            "iat": issued_at,
            "exp": issued_at + self._expires_in_seconds,
        }
        header = {"alg": self._algorithm, "typ": "JWT"}
        signing_input = ".".join(
            (
                _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
                _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
            )
        )
        signature = hmac.new(self._secret_key, signing_input.encode("ascii"), hashlib.sha256).digest()
        return f"{signing_input}.{_b64url_encode(signature)}"

    def decode_access_token(self, token: str, *, now: int | None = None) -> dict[str, str | int]:
        """Validate a token and return its payload."""
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
        except ValueError as exc:
            raise AuthTokenInvalidError() from exc

        try:
            header = json.loads(_b64url_decode(encoded_header))
            payload = json.loads(_b64url_decode(encoded_payload))
        except (ValueError, json.JSONDecodeError) as exc:
            raise AuthTokenInvalidError() from exc

        if header.get("alg") != self._algorithm or header.get("typ") != "JWT":
            raise AuthTokenInvalidError()

        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(self._secret_key, signing_input, hashlib.sha256).digest()
        try:
            actual_signature = _b64url_decode(encoded_signature)
        except ValueError as exc:
            raise AuthTokenInvalidError() from exc
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise AuthTokenInvalidError()

        exp = payload.get("exp")
        sub = payload.get("sub")
        email = payload.get("email")
        iat = payload.get("iat")
        if not isinstance(exp, int) or not isinstance(iat, int) or not isinstance(sub, str) or not isinstance(email, str):
            raise AuthTokenInvalidError()
        current_time = now or int(time.time())
        if exp <= current_time:
            raise AuthTokenExpiredError()
        return payload
