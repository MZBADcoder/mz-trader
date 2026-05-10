"""API route tests for auth, watchlist, and ticker search endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.errors import register_exception_handlers
from api.middleware.request_context import RequestContextMiddleware
from api.routers import router as api_router
from application.services import AuthSession
from domain.entities import TickerSearchResult, User, WatchlistItem
from domain.exceptions import (
    AuthEmailAlreadyExistsError,
    AuthTokenExpiredError,
)


def _user() -> User:
    now = datetime.now(UTC)
    return User(
        id="6f9ee6e5-fcd8-4567-a356-b3d8801cb6ef",
        email="user@example.com",
        password_hash="hashed",
        created_at=now,
        updated_at=now,
    )


@dataclass(slots=True)
class FakeRegisterService:
    should_fail: bool = False

    async def execute(self, *, email: str, password: str) -> AuthSession:
        if self.should_fail:
            raise AuthEmailAlreadyExistsError()
        return AuthSession(
            user=_user(), access_token="token-123", token_type="bearer", expires_in=3600
        )


@dataclass(slots=True)
class FakeLoginService:
    async def execute(self, *, email: str, password: str) -> AuthSession:
        return AuthSession(
            user=_user(), access_token="token-123", token_type="bearer", expires_in=3600
        )


@dataclass(slots=True)
class FakeCurrentUserService:
    expired: bool = False

    async def execute(self, *, token: str) -> User:
        if self.expired:
            raise AuthTokenExpiredError()
        return _user()


@dataclass(slots=True)
class FakeWatchlistService:
    async def execute(self, *, user_id: str):
        return [
            WatchlistItem(
                id="item-1",
                user_id=user_id,
                ticker="AAPL",
                position=0,
                created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
            )
        ]


@dataclass(slots=True)
class FakeAddWatchlistItemService:
    async def execute(self, *, user_id: str, ticker: str) -> WatchlistItem:
        return WatchlistItem(
            id="item-1",
            user_id=user_id,
            ticker=ticker.strip().upper(),
            position=0,
            created_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
        )


@dataclass(slots=True)
class FakeUpdateWatchlistService:
    async def execute(self, *, user_id: str, tickers: list[str]) -> list[WatchlistItem]:
        return [
            WatchlistItem(
                id=f"item-{ticker}",
                user_id=user_id,
                ticker=ticker.strip().upper(),
                position=position,
                created_at=datetime(2026, 3, 13, 10, position, tzinfo=UTC),
            )
            for position, ticker in enumerate(tickers)
        ]


@dataclass(slots=True)
class FakeDeleteWatchlistItemService:
    async def execute(self, *, user_id: str, ticker: str) -> None:
        return None


@dataclass(slots=True)
class FakeSearchReferenceService:
    async def execute(self, *, query: str, limit: int) -> list[TickerSearchResult]:
        return [
            TickerSearchResult(
                ticker="AAPL",
                name="Apple Inc.",
                primary_exchange="XNAS",
                type="CS",
                active=True,
            )
        ]


class FakeContainer:
    def __init__(
        self, *, duplicate_register: bool = False, expired_token: bool = False
    ) -> None:
        self._duplicate_register = duplicate_register
        self._expired_token = expired_token

    def get_register_user_service(self) -> FakeRegisterService:
        return FakeRegisterService(should_fail=self._duplicate_register)

    def get_login_user_service(self) -> FakeLoginService:
        return FakeLoginService()

    def get_current_user_service(self) -> FakeCurrentUserService:
        return FakeCurrentUserService(expired=self._expired_token)

    def get_watchlist_service(self) -> FakeWatchlistService:
        return FakeWatchlistService()

    def get_add_watchlist_item_service(self) -> FakeAddWatchlistItemService:
        return FakeAddWatchlistItemService()

    def get_delete_watchlist_item_service(self) -> FakeDeleteWatchlistItemService:
        return FakeDeleteWatchlistItemService()

    def get_update_watchlist_service(self) -> FakeUpdateWatchlistService:
        return FakeUpdateWatchlistService()

    def get_search_tickers_service(self) -> FakeSearchReferenceService:
        return FakeSearchReferenceService()


def _build_app(container: FakeContainer) -> FastAPI:
    app = FastAPI()
    app.state.container = container
    app.add_middleware(RequestContextMiddleware, request_id_header="X-Request-ID")
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


def test_register_route_returns_auth_session() -> None:
    client = TestClient(_build_app(FakeContainer()))

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "secret123"},
    )

    assert response.status_code == 201
    assert response.json()["user"]["id"] == "6f9ee6e5-fcd8-4567-a356-b3d8801cb6ef"
    assert response.json()["access_token"] == "token-123"


def test_register_route_returns_shared_error_payload() -> None:
    client = TestClient(_build_app(FakeContainer(duplicate_register=True)))

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "secret123"},
        headers={"X-Request-ID": "req-12345678"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AUTH_EMAIL_ALREADY_EXISTS"
    assert response.json()["error"]["request_id"] == "req-12345678"


def test_watchlist_route_requires_authentication() -> None:
    client = TestClient(_build_app(FakeContainer()))

    response = client.get("/api/v1/watchlist", headers={"X-Request-ID": "req-87654321"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.json()["error"]["request_id"] == "req-87654321"


def test_register_route_rejects_short_password() -> None:
    client = TestClient(_build_app(FakeContainer()))

    response = client.post(
        "/api/v1/auth/register", json={"email": "user@example.com", "password": "short"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_auth_me_route_returns_token_expired() -> None:
    client = TestClient(_build_app(FakeContainer(expired_token=True)))

    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer expired-token"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_EXPIRED"


def test_ticker_search_route_returns_items() -> None:
    client = TestClient(_build_app(FakeContainer()))

    response = client.get(
        "/api/v1/ticker-search/search",
        params={"query": "apple"},
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["ticker"] == "AAPL"


def test_watchlist_update_route_returns_ordered_items() -> None:
    client = TestClient(_build_app(FakeContainer()))

    response = client.patch(
        "/api/v1/watchlist",
        json={"tickers": ["nvda", "aapl"]},
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert [
        (item["ticker"], item["position"]) for item in response.json()["items"]
    ] == [
        ("NVDA", 0),
        ("AAPL", 1),
    ]
