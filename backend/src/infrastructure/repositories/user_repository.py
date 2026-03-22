"""User repository implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import User
from domain.rules import normalize_email
from infrastructure.db.mappers import to_user_entity
from infrastructure.db.models import UserModel


class UserRepository:
    """Persist and load users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by normalized email."""
        normalized = normalize_email(email)
        stmt = select(UserModel).where(UserModel.email == normalized).limit(1)
        model = await self._session.scalar(stmt)
        if model is None:
            return None
        return to_user_entity(model)

    async def get_by_id(self, user_id: str) -> User | None:
        """Fetch a user by id."""
        stmt = select(UserModel).where(UserModel.id == uuid.UUID(user_id)).limit(1)
        model = await self._session.scalar(stmt)
        if model is None:
            return None
        return to_user_entity(model)

    async def add(self, *, email: str, password_hash: str) -> User:
        """Persist a new user."""
        now = datetime.now(UTC)
        model = UserModel(
            id=uuid.uuid4(),
            email=normalize_email(email),
            password_hash=password_hash,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return to_user_entity(model)
