"""Authentication service tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from application.services.auth import GetCurrentUserService, LoginUserService, RegisterUserService
from domain.entities import User
from domain.exceptions import AuthEmailAlreadyExistsError, AuthInvalidCredentialsError, AuthTokenInvalidError, ValidationError


def _user(*, user_id: str = "6f9ee6e5-fcd8-4567-a356-b3d8801cb6ef", email: str = "user@example.com") -> User:
    now = datetime.now(UTC)
    return User(id=user_id, email=email, password_hash="hashed:secret", created_at=now, updated_at=now)


class FakeUserRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, User] = {}
        self.users_by_id: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self.users_by_email.get(email)

    async def get_by_id(self, user_id: str) -> User | None:
        return self.users_by_id.get(user_id)

    async def add(self, *, email: str, password_hash: str) -> User:
        user = _user(email=email)
        user.password_hash = password_hash
        self.users_by_email[email] = user
        self.users_by_id[user.id] = user
        return user


class FakeWatchlistRepository:
    async def list_by_user(self, user_id: str):
        return []


class FakeUow:
    def __init__(self, users: FakeUserRepository) -> None:
        self.users = users
        self.watchlist = FakeWatchlistRepository()
        self.committed = False

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeUowFactory:
    def __init__(self, uow: FakeUow) -> None:
        self._uow = uow

    def build(self) -> FakeUow:
        return self._uow


class FakePasswordHasher:
    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed:{password}"


@dataclass(slots=True)
class FakeJwtService:
    expires_in_seconds: int = 3600
    payload: dict[str, str | int] | None = None

    def issue_access_token(self, *, user_id: str, email: str) -> str:
        return f"token-for:{user_id}:{email}"

    def decode_access_token(self, token: str) -> dict[str, str | int]:
        if self.payload is None:
            raise AuthTokenInvalidError()
        return self.payload


def test_register_user_service_normalizes_email_and_returns_token() -> None:
    users = FakeUserRepository()
    uow = FakeUow(users)
    service = RegisterUserService(
        uow_factory=FakeUowFactory(uow),
        password_hasher=FakePasswordHasher(),
        jwt_service=FakeJwtService(),
    )

    result = asyncio.run(service.execute(email="  USER@Example.com ", password="secret123"))

    assert result.user.email == "user@example.com"
    assert result.access_token == f"token-for:{result.user.id}:user@example.com"
    assert uow.committed is True


def test_register_user_service_rejects_duplicate_email() -> None:
    users = FakeUserRepository()
    existing = _user()
    users.users_by_email[existing.email] = existing
    uow = FakeUow(users)
    service = RegisterUserService(
        uow_factory=FakeUowFactory(uow),
        password_hasher=FakePasswordHasher(),
        jwt_service=FakeJwtService(),
    )

    with pytest.raises(AuthEmailAlreadyExistsError):
        asyncio.run(service.execute(email=existing.email, password="secret123"))


def test_login_user_service_rejects_invalid_password() -> None:
    users = FakeUserRepository()
    existing = _user()
    users.users_by_email[existing.email] = existing
    users.users_by_id[existing.id] = existing
    service = LoginUserService(
        uow_factory=FakeUowFactory(FakeUow(users)),
        password_hasher=FakePasswordHasher(),
        jwt_service=FakeJwtService(),
    )

    with pytest.raises(AuthInvalidCredentialsError):
        asyncio.run(service.execute(email=existing.email, password="wrong"))


def test_register_user_service_rejects_short_password() -> None:
    users = FakeUserRepository()
    service = RegisterUserService(
        uow_factory=FakeUowFactory(FakeUow(users)),
        password_hasher=FakePasswordHasher(),
        jwt_service=FakeJwtService(),
    )

    with pytest.raises(ValidationError):
        asyncio.run(service.execute(email="user@example.com", password="short"))


def test_get_current_user_service_rejects_invalid_subject() -> None:
    users = FakeUserRepository()
    service = GetCurrentUserService(
        uow_factory=FakeUowFactory(FakeUow(users)),
        jwt_service=FakeJwtService(payload={"sub": "missing-user", "email": "u@example.com", "iat": 1, "exp": 2}),
    )

    with pytest.raises(AuthTokenInvalidError):
        asyncio.run(service.execute(token="token"))
