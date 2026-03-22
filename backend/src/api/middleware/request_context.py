"""HTTP request context and access logging middleware."""

from __future__ import annotations

import logging
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bootstrap.request_context import (
    RequestLogContext,
    bind_request_context,
    generate_request_id,
    is_valid_request_id,
    reset_request_context,
    set_request_context,
)


logger = logging.getLogger("api.request")


class RequestContextMiddleware:
    """Attach request metadata to a contextvar and emit access logs."""

    def __init__(self, app: ASGIApp, request_id_header: str = "X-Request-ID") -> None:
        self.app = app
        self.request_id_header = request_id_header

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        client_request_id = headers.get(self.request_id_header)
        request_id = client_request_id if is_valid_request_id(client_request_id) else generate_request_id()

        token = set_request_context(
            RequestLogContext(
                request_id=request_id,
                method=scope["method"],
                path=scope.get("path", ""),
            )
        )

        started_at = perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers[self.request_id_header] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            context = bind_request_context(status_code=status_code, latency_ms=latency_ms)
            logger.exception("unhandled exception", extra=context.as_log_extra())
            raise
        else:
            latency_ms = round((perf_counter() - started_at) * 1000, 2)
            context = bind_request_context(status_code=status_code, latency_ms=latency_ms)
            logger.info("request completed", extra=context.as_log_extra())
        finally:
            reset_request_context(token)
