"""Authentication DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuthRequest(BaseModel):
    """Register or login payload."""

    email: str
    password: str


class UserResponse(BaseModel):
    """Public user shape returned by the auth endpoints."""

    id: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class AuthSessionResponse(BaseModel):
    """Auth response payload."""

    user: UserResponse
    access_token: str
    token_type: str
    expires_in: int

    model_config = ConfigDict(from_attributes=True)


class CurrentUserResponse(BaseModel):
    """Current authenticated user response."""

    user: UserResponse

    model_config = ConfigDict(from_attributes=True)
