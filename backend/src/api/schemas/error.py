"""Error response DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorBody(BaseModel):
    """Stable error body."""

    code: str
    message: str
    detail: str
    request_id: str

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Envelope for error responses."""

    error: ErrorBody

    model_config = ConfigDict(from_attributes=True)
