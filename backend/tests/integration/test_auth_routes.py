"""Integration tests for auth, watchlist, and ticker-search routes."""

from __future__ import annotations

import asyncio

import pytest

from infrastructure.security.jwt_service import JwtService
from infrastructure.repositories.watchlist_repository import WatchlistRepository


def _register_user(client, *, email: str, password: str = "secret123") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    return response


def _authenticate(client, *, email: str, password: str = "secret123") -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return response


def _auth_headers(access_token: str, request_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if request_id is not None:
        headers["X-Request-ID"] = request_id
    return headers


def test_register_then_me_returns_persisted_user(client) -> None:
    register_response = _register_user(
        client,
        email="  USER@example.com ",
    )

    assert register_response.status_code == 201

    payload = register_response.json()
    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["user"]["id"] == payload["user"]["id"]
    assert me_response.json()["user"]["email"] == "user@example.com"


def test_register_rejects_duplicate_email_with_shared_error_payload(client) -> None:
    first_response = _register_user(
        client,
        email="duplicate@example.com",
    )
    second_response = _register_user(
        client,
        email="DUPLICATE@example.com",
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "AUTH_EMAIL_ALREADY_EXISTS"
    assert second_response.json()["error"]["request_id"]


def test_login_returns_auth_session_and_supports_auth_me(client) -> None:
    register_response = _register_user(
        client,
        email="user@example.com",
    )

    assert register_response.status_code == 201

    login_response = _authenticate(
        client,
        email="user@example.com",
    )

    assert login_response.status_code == 200
    payload = login_response.json()

    me_response = client.get(
        "/api/v1/auth/me",
        headers=_auth_headers(payload["access_token"]),
    )

    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "user@example.com"
    assert me_response.status_code == 200
    assert me_response.json()["user"]["id"] == payload["user"]["id"]


def test_login_rejects_invalid_credentials(client) -> None:
    register_response = _register_user(
        client,
        email="user@example.com",
    )

    assert register_response.status_code == 201

    response = _authenticate(
        client,
        email="user@example.com",
        password="wrong-password",
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    assert response.json()["error"]["request_id"]


def test_watchlist_route_requires_authentication(client) -> None:
    response = client.get(
        "/api/v1/watchlist", headers={"X-Request-ID": "req-watchlist-auth"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.json()["error"]["request_id"] == "req-watchlist-auth"


def test_watchlist_update_route_requires_authentication(client) -> None:
    response = client.patch(
        "/api/v1/watchlist",
        json={"tickers": []},
        headers={"X-Request-ID": "req-watchlist-update-auth"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.json()["error"]["request_id"] == "req-watchlist-update-auth"


def test_auth_me_rejects_invalid_token(client) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers=_auth_headers("not-a-valid-jwt"),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_auth_me_rejects_expired_token(client, integration_settings) -> None:
    register_response = _register_user(
        client,
        email="expired@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()
    jwt_service = JwtService(
        secret_key=integration_settings.app_secret_key,
        expires_in_seconds=integration_settings.auth_access_token_ttl_seconds,
        algorithm=integration_settings.auth_jwt_algorithm,
    )
    expired_token = jwt_service.issue_access_token(
        user_id=payload["user"]["id"],
        email=payload["user"]["email"],
        now=1,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers=_auth_headers(expired_token),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_EXPIRED"


def test_watchlist_route_reads_only_current_users_items_in_persisted_order(
    client, session_factory
) -> None:
    first_response = _register_user(
        client,
        email="user@example.com",
    )
    second_response = _register_user(
        client,
        email="other@example.com",
    )
    first_payload = first_response.json()
    second_payload = second_response.json()

    async def seed_watchlist() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            await repository.add(user_id=first_payload["user"]["id"], ticker="AAPL")
            await repository.add(user_id=first_payload["user"]["id"], ticker="MSFT")
            await repository.add(user_id=second_payload["user"]["id"], ticker="TSLA")
            await session.commit()

    asyncio.run(seed_watchlist())

    response = client.get(
        "/api/v1/watchlist",
        headers=_auth_headers(first_payload["access_token"]),
    )

    assert response.status_code == 200
    assert [item["ticker"] for item in response.json()["items"]] == ["AAPL", "MSFT"]
    assert [item["position"] for item in response.json()["items"]] == [0, 1]


def test_watchlist_update_reorders_existing_tickers_and_persists_order(
    client, session_factory
) -> None:
    register_response = _register_user(
        client,
        email="watchlist-reorder@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    async def seed_watchlist() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            await repository.add(user_id=payload["user"]["id"], ticker="AAPL")
            await repository.add(user_id=payload["user"]["id"], ticker="NVDA")
            await repository.add(user_id=payload["user"]["id"], ticker="MSFT")
            await session.commit()

    asyncio.run(seed_watchlist())

    update_response = client.patch(
        "/api/v1/watchlist",
        json={"tickers": ["msft", "aapl", "nvda"]},
        headers=_auth_headers(payload["access_token"]),
    )
    list_response = client.get(
        "/api/v1/watchlist",
        headers=_auth_headers(payload["access_token"]),
    )

    assert update_response.status_code == 200
    assert [
        (item["ticker"], item["position"]) for item in update_response.json()["items"]
    ] == [
        ("MSFT", 0),
        ("AAPL", 1),
        ("NVDA", 2),
    ]
    assert [
        (item["ticker"], item["position"]) for item in list_response.json()["items"]
    ] == [
        ("MSFT", 0),
        ("AAPL", 1),
        ("NVDA", 2),
    ]


def test_watchlist_update_rejects_ticker_set_mismatch(client, session_factory) -> None:
    register_response = _register_user(
        client,
        email="watchlist-reorder-invalid@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    async def seed_watchlist() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            await repository.add(user_id=payload["user"]["id"], ticker="AAPL")
            await repository.add(user_id=payload["user"]["id"], ticker="NVDA")
            await session.commit()

    asyncio.run(seed_watchlist())

    response = client.patch(
        "/api/v1/watchlist",
        json={"tickers": ["AAPL", "MSFT"]},
        headers=_auth_headers(payload["access_token"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WATCHLIST_ORDER_INVALID"


def test_watchlist_update_does_not_affect_other_users(client, session_factory) -> None:
    first_response = _register_user(
        client,
        email="watchlist-reorder-a@example.com",
    )
    second_response = _register_user(
        client,
        email="watchlist-reorder-b@example.com",
    )
    first_payload = first_response.json()
    second_payload = second_response.json()

    async def seed_watchlists() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            await repository.add(user_id=first_payload["user"]["id"], ticker="AAPL")
            await repository.add(user_id=first_payload["user"]["id"], ticker="MSFT")
            await repository.add(user_id=second_payload["user"]["id"], ticker="AAPL")
            await repository.add(user_id=second_payload["user"]["id"], ticker="MSFT")
            await session.commit()

    asyncio.run(seed_watchlists())

    update_response = client.patch(
        "/api/v1/watchlist",
        json={"tickers": ["MSFT", "AAPL"]},
        headers=_auth_headers(first_payload["access_token"]),
    )
    second_list_response = client.get(
        "/api/v1/watchlist",
        headers=_auth_headers(second_payload["access_token"]),
    )

    assert update_response.status_code == 200
    assert [item["ticker"] for item in update_response.json()["items"]] == [
        "MSFT",
        "AAPL",
    ]
    assert [item["ticker"] for item in second_list_response.json()["items"]] == [
        "AAPL",
        "MSFT",
    ]


def test_watchlist_add_item_returns_uppercase_and_persists_it(
    client,
    integration_settings,
) -> None:
    if not integration_settings.massive_api_key:
        pytest.skip("Massive API key is required for live watchlist integration tests.")

    register_response = _register_user(
        client,
        email="watchlist-add@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    add_response = client.post(
        "/api/v1/watchlist/items",
        json={"ticker": " aapl "},
        headers=_auth_headers(payload["access_token"]),
    )
    list_response = client.get(
        "/api/v1/watchlist",
        headers=_auth_headers(payload["access_token"]),
    )

    assert add_response.status_code == 201
    assert add_response.json()["item"]["ticker"] == "AAPL"
    assert add_response.json()["item"]["position"] == 0
    assert [item["ticker"] for item in list_response.json()["items"]] == ["AAPL"]


def test_watchlist_add_rejects_duplicate_ticker(client, integration_settings) -> None:
    if not integration_settings.massive_api_key:
        pytest.skip("Massive API key is required for live watchlist integration tests.")

    register_response = _register_user(
        client,
        email="watchlist-duplicate@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    first_response = client.post(
        "/api/v1/watchlist/items",
        json={"ticker": "AAPL"},
        headers=_auth_headers(payload["access_token"]),
    )
    second_response = client.post(
        "/api/v1/watchlist/items",
        json={"ticker": "AAPL"},
        headers=_auth_headers(payload["access_token"]),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "WATCHLIST_TICKER_DUPLICATE"


def test_watchlist_add_rejects_invalid_ticker_format(client) -> None:
    register_response = _register_user(
        client,
        email="watchlist-invalid@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    response = client.post(
        "/api/v1/watchlist/items",
        json={"ticker": "AAPL!"},
        headers=_auth_headers(payload["access_token"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WATCHLIST_TICKER_INVALID"


def test_watchlist_add_rejects_unsupported_ticker(client, integration_settings) -> None:
    if not integration_settings.massive_api_key:
        pytest.skip("Massive API key is required for live watchlist integration tests.")

    register_response = _register_user(
        client,
        email="watchlist-unsupported@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    response = client.post(
        "/api/v1/watchlist/items",
        json={"ticker": "ZZZZZZZZ"},
        headers=_auth_headers(payload["access_token"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WATCHLIST_TICKER_NOT_SUPPORTED"


def test_watchlist_delete_item_removes_ticker(client, session_factory) -> None:
    register_response = _register_user(
        client,
        email="watchlist-delete@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    async def seed_watchlist() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            await repository.add(user_id=payload["user"]["id"], ticker="AAPL")
            await repository.add(user_id=payload["user"]["id"], ticker="MSFT")
            await repository.add(user_id=payload["user"]["id"], ticker="NVDA")
            await session.commit()

    asyncio.run(seed_watchlist())

    delete_response = client.delete(
        "/api/v1/watchlist/items/AAPL",
        headers=_auth_headers(payload["access_token"]),
    )
    list_response = client.get(
        "/api/v1/watchlist",
        headers=_auth_headers(payload["access_token"]),
    )

    assert delete_response.status_code == 204
    assert list_response.status_code == 200
    assert [
        (item["ticker"], item["position"]) for item in list_response.json()["items"]
    ] == [
        ("MSFT", 0),
        ("NVDA", 1),
    ]


def test_watchlist_delete_rejects_missing_ticker(client) -> None:
    register_response = _register_user(
        client,
        email="watchlist-missing@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    response = client.delete(
        "/api/v1/watchlist/items/AAPL",
        headers=_auth_headers(payload["access_token"]),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WATCHLIST_TICKER_NOT_FOUND"


def test_ticker_search_returns_candidates_for_company_query(
    client, integration_settings
) -> None:
    if not integration_settings.massive_api_key:
        pytest.skip(
            "Massive API key is required for live ticker search integration tests."
        )

    register_response = _register_user(
        client,
        email="ticker-search@example.com",
    )

    assert register_response.status_code == 201
    payload = register_response.json()

    response = client.get(
        "/api/v1/ticker-search/search",
        params={"query": "apple", "limit": 5},
        headers=_auth_headers(payload["access_token"]),
    )

    assert response.status_code == 200
    returned_tickers = [item["ticker"] for item in response.json()["items"]]
    assert "AAPL" in returned_tickers
