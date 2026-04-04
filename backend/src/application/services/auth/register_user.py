"""Register user use case."""

from __future__ import annotations

from domain.exceptions import AuthEmailAlreadyExistsError
from domain.rules import normalize_email, validate_password
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.security.jwt_service import JwtService
from infrastructure.security.password_hasher import PBKDF2PasswordHasher

from application.services.auth.auth_session import AuthSession


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
        validated_password = validate_password(password)
        async with self._uow_factory.build() as uow:
            existing_user = await uow.users.get_by_email(normalized_email)
            if existing_user is not None:
                raise AuthEmailAlreadyExistsError()

            user = await uow.users.add(
                email=normalized_email,
                password_hash=self._password_hasher.hash_password(validated_password),
            )
            await uow.commit()

        access_token = self._jwt_service.issue_access_token(user_id=user.id, email=user.email)
        return AuthSession(
            user=user,
            access_token=access_token,
            token_type="bearer",
            expires_in=self._jwt_service.expires_in_seconds,
        )
