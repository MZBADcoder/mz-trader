"""Authentication session DTO for the application layer."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities import User


@dataclass(slots=True)
class AuthSession:
    """Authenticated session payload returned to the API layer."""

    user: User
    access_token: str
    token_type: str
    expires_in: int
