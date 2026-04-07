"""Integration tests for repository behavior against PostgreSQL."""

from __future__ import annotations

import asyncio

import pytest

from domain.exceptions import AuthEmailAlreadyExistsError
from infrastructure.repositories.user_repository import UserRepository


def test_user_repository_persists_normalized_email(session_factory) -> None:
    async def exercise_repository() -> None:
        async with session_factory() as session:
            repository = UserRepository(session)
            created = await repository.add(email="  USER@Example.com ", password_hash="hashed")
            await session.commit()

        async with session_factory() as session:
            repository = UserRepository(session)
            loaded = await repository.get_by_email("user@example.com")

        assert created.email == "user@example.com"
        assert loaded is not None
        assert loaded.email == "user@example.com"
        assert loaded.id == created.id

    asyncio.run(exercise_repository())


def test_user_repository_raises_domain_error_on_duplicate_email(session_factory) -> None:
    async def exercise_repository() -> None:
        async with session_factory() as session:
            repository = UserRepository(session)
            await repository.add(email="user@example.com", password_hash="hashed")
            await session.commit()

        async with session_factory() as session:
            repository = UserRepository(session)
            with pytest.raises(AuthEmailAlreadyExistsError):
                await repository.add(email="USER@example.com", password_hash="hashed-2")

    asyncio.run(exercise_repository())
