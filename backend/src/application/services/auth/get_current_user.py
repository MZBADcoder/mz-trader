"""Get current user use case."""

from __future__ import annotations

from uuid import UUID

from domain.entities import User
from domain.exceptions import AuthTokenInvalidError
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.security.jwt_service import JwtService


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
        try:
            UUID(user_id)
        except ValueError as exc:
            raise AuthTokenInvalidError() from exc

        async with self._uow_factory.build() as uow:
            user = await uow.users.get_by_id(user_id)

        if user is None:
            raise AuthTokenInvalidError()
        return user
