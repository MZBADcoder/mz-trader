"""Dependency wiring entrypoint for the API layer."""

from __future__ import annotations

from fastapi import Depends, Header, Request

from application.container import Container
from application.services import (
    AddWatchlistItemService,
    GetCurrentUserService,
    GetWatchlistService,
    LoginUserService,
    RegisterUserService,
    SearchReferenceTickersService,
    DeleteWatchlistItemService,
)
from domain.entities import User
from domain.exceptions import AuthenticationRequiredError, AuthTokenInvalidError


def get_container(request: Request) -> Container:
    """Return the application container stored on app state."""
    return request.app.state.container


def get_register_user_service(container: Container = Depends(get_container)) -> RegisterUserService:
    return container.get_register_user_service()


def get_login_user_service(container: Container = Depends(get_container)) -> LoginUserService:
    return container.get_login_user_service()


def get_current_user_service(container: Container = Depends(get_container)) -> GetCurrentUserService:
    return container.get_current_user_service()


def get_watchlist_service(container: Container = Depends(get_container)) -> GetWatchlistService:
    return container.get_watchlist_service()


def get_add_watchlist_item_service(container: Container = Depends(get_container)) -> AddWatchlistItemService:
    return container.get_add_watchlist_item_service()


def get_delete_watchlist_item_service(
    container: Container = Depends(get_container),
) -> DeleteWatchlistItemService:
    return container.get_delete_watchlist_item_service()


def get_search_reference_tickers_service(
    container: Container = Depends(get_container),
) -> SearchReferenceTickersService:
    return container.get_search_reference_tickers_service()


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise AuthenticationRequiredError()

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials:
        raise AuthTokenInvalidError()
    return credentials


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    service: GetCurrentUserService = Depends(get_current_user_service),
) -> User:
    """Resolve the authenticated user from the bearer token."""
    token = _extract_bearer_token(authorization)
    return await service.execute(token=token)
