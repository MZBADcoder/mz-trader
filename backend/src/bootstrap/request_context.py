"""Request-scoped logging context helpers."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
from uuid import uuid4


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


@dataclass(slots=True)
class RequestLogContext:
    """Stable request metadata attached to log records."""

    request_id: str | None = None
    user_id: str | None = None
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    latency_ms: float | None = None
    error_code: str | None = None
    ticker: str | None = None
    upstream_service: str | None = None

    def as_log_extra(self) -> dict[str, str | int | float]:
        """Return a compact dict suitable for logging extra payloads."""
        return {key: value for key, value in asdict(self).items() if value is not None}


_REQUEST_CONTEXT: ContextVar[RequestLogContext | None] = ContextVar("request_log_context", default=None)


def generate_request_id() -> str:
    """Generate a request id that is safe to echo in logs and headers."""
    return uuid4().hex


def is_valid_request_id(value: str | None) -> bool:
    """Validate a client supplied request id."""
    if value is None:
        return False
    return bool(REQUEST_ID_PATTERN.fullmatch(value))


def get_request_context() -> RequestLogContext:
    """Return the current request context or an empty context."""
    context = _REQUEST_CONTEXT.get()
    if context is None:
        return RequestLogContext()
    return context


def set_request_context(context: RequestLogContext) -> Token[RequestLogContext | None]:
    """Replace the active request context."""
    return _REQUEST_CONTEXT.set(context)


def bind_request_context(**values: str | int | float | None) -> RequestLogContext:
    """Update selected request context fields."""
    current = get_request_context()
    next_context = replace(current, **values)
    _REQUEST_CONTEXT.set(next_context)
    return next_context


def reset_request_context(token: Token[RequestLogContext | None]) -> None:
    """Restore the previous request context."""
    _REQUEST_CONTEXT.reset(token)
