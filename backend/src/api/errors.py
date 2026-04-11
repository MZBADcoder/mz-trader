"""HTTP error translation helpers."""

from __future__ import annotations

import logging
from typing import Any, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.schemas.error import ErrorBody, ErrorResponse
from bootstrap.request_context import bind_request_context, get_request_context
from domain.exceptions import AppError, InternalError, ValidationError


logger = logging.getLogger("api.errors")


def _build_error_response(*, status_code: int, code: str, message: str, detail: str) -> JSONResponse:
    request_id = get_request_context().request_id or ""
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            detail=detail,
            request_id=request_id,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def _summarize_validation_error(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", []))
        message = str(error.get("msg", "Invalid value"))
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Serialize stable business errors."""
    bind_request_context(error_code=exc.code)
    return _build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        detail=exc.detail,
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Map FastAPI validation errors to the shared error payload."""
    detail = _summarize_validation_error(exc)
    error = ValidationError(detail=detail)
    bind_request_context(error_code=error.code)
    return _build_error_response(
        status_code=error.status_code,
        code=error.code,
        message=error.message,
        detail=error.detail,
    )


async def internal_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Hide unexpected exceptions behind a stable payload."""
    error = InternalError()
    bind_request_context(error_code=error.code)
    logger.exception("unhandled api exception")
    return _build_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=error.code,
        message=error.message,
        detail=error.detail,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register API-level exception handlers."""
    # FastAPI dispatches by registered exception type, but its public handler
    # annotation is wider than these specific business handlers.
    app.add_exception_handler(AppError, cast(Any, app_error_handler))
    app.add_exception_handler(RequestValidationError, cast(Any, validation_error_handler))
    app.add_exception_handler(Exception, internal_error_handler)
