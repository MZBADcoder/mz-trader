"""User domain entity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class User:
    """Registered user."""

    id: str
    email: str
    password_hash: str
    created_at: datetime
    updated_at: datetime
