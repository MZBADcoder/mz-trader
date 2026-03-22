"""Authentication use cases."""

from __future__ import annotations

from dataclasses import dataclass

from domain.entities import User
from domain.exceptions import AuthEmailAlreadyExistsError, AuthInvalidCredentialsError, AuthTokenInvalidError
from domain.rules import normalize_email
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external.jwt_service import JwtService
from infrastructure.external.password_hasher import PBKDF2PasswordHasher


@dataclass(slots=True)
class AuthSession:
    """Authenticated session payload returned to the API layer."""

    user: User
    access_token: str
    token_type: str
    expires_in: int


class RegisterUserService:
    """Create a user account and issue an access token."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        password_hasher: PBKDF2PasswordHasher,
        jwt_service: JwtService,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._jwt_service = jwt_service

    async def execute(self, *, email: str, password: str) -> AuthSession:
        normalized_email = normalize_email(email)
        async with self._uow_factory.build() as uow:
            assert uow.users is not None
            existing_user = await uow.users.get_by_email(normalized_email)
            if existing_user is not None:
                raise AuthEmailAlreadyExistsError()

            user = await uow.users.add(
                email=normalized_email,
                password_hash=self._password_hasher.hash_password(password),
            )
            await uow.commit()

        access_token = self._jwt_service.issue_access_token(user_id=user.id, email=user.email)
        return AuthSession(
            user=user,
            access_token=access_token,
            token_type="bearer",
            expires_in=self._jwt_service.expires_in_seconds,
        )


class LoginUserService:
    """Verify credentials and issue an access token."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        password_hasher: PBKDF2PasswordHasher,
        jwt_service: JwtService,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._jwt_service = jwt_service

    async def execute(self, *, email: str, password: str) -> AuthSession:
        normalized_email = normalize_email(email)
        async with self._uow_factory.build() as uow:
            assert uow.users is not None
            user = await uow.users.get_by_email(normalized_email)

        if user is None or not self._password_hasher.verify_password(password, user.password_hash):
            raise AuthInvalidCredentialsError()

        access_token = self._jwt_service.issue_access_token(user_id=user.id, email=user.email)
        return AuthSession(
            user=user,
            access_token=access_token,
            token_type="bearer",
            expires_in=self._jwt_service.expires_in_seconds,
        )


class GetCurrentUserService:
    """Load the authenticated user from a bearer token."""

    def __init__(self, *, uow_factory: SqlAlchemyUnitOfWorkFactory, jwt_service: JwtService) -> None:
        self._uow_factory = uow_factory
        self._jwt_service = jwt_service

    async def execute(self, *, token: str) -> User:
        payload = self._jwt_service.decode_access_token(token)
        user_id = payload.get("sub")
        if not isinstance(user_id, str):
            raise AuthTokenInvalidError()

        async with self._uow_factory.build() as uow:
            assert uow.users is not None
            user = await uow.users.get_by_id(user_id)

        if user is None:
            raise AuthTokenInvalidError()
        return user
