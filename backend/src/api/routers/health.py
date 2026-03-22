"""System health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.health import HealthResponse
from bootstrap.request_context import get_request_context


router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    """Expose a lightweight endpoint for smoke checks."""
    request_context = get_request_context()
    return HealthResponse(status="ok", request_id=request_context.request_id or "")
