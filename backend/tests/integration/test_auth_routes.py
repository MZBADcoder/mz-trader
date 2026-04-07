"""Integration tests for auth and watchlist routes against PostgreSQL."""

from __future__ import annotations

import asyncio

from infrastructure.repositories.watchlist_repository import WatchlistRepository


def test_register_then_me_returns_persisted_user(client) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "  USER@example.com ", "password": "secret123"},
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


def test_watchlist_route_reads_items_from_real_database(client, session_factory) -> None:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "secret123"},
    )
    payload = register_response.json()

    async def seed_watchlist() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            await repository.add(user_id=payload["user"]["id"], ticker="AAPL")
            await session.commit()

    asyncio.run(seed_watchlist())

    response = client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["ticker"] == "AAPL"
