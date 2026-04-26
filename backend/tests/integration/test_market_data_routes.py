"""Integration tests for market-data routes with real app wiring."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime
from typing import Any

from fastapi.testclient import TestClient
import httpx

from application.container import Container
from domain.entities import CanonicalBar, Snapshot
from infrastructure.external import MassiveSnapshotClient
from infrastructure.repositories.market_bar_repository import MarketBarRepository
from infrastructure.repositories.market_terminal_snapshot_repository import MarketTerminalSnapshotRepository
from infrastructure.repositories.watchlist_repository import WatchlistRepository
from main import create_app
from settings import Settings


def _register_and_authenticate(client, *, email: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["user"]["id"], payload["access_token"]


def _seed_snapshot(redis_client, snapshot: Snapshot) -> None:
    redis_client.set(
        f"snapshot:{snapshot.ticker}",
        json.dumps(
            {
                "ticker": snapshot.ticker,
                "last": snapshot.last,
                "regular_close": snapshot.regular_close,
                "change": snapshot.change,
                "change_pct": snapshot.change_pct,
                "open": snapshot.open,
                "high": snapshot.high,
                "low": snapshot.low,
                "volume": snapshot.volume,
                "prev_close": snapshot.prev_close,
                "market_status": snapshot.market_status,
                "session": snapshot.session,
                "trading_day": snapshot.trading_day.isoformat() if snapshot.trading_day is not None else None,
                "last_session": snapshot.last_session,
                "last_trade_at": snapshot.last_trade_at.astimezone(UTC).isoformat()
                if snapshot.last_trade_at is not None
                else None,
                "delay_minutes": snapshot.delay_minutes,
                "is_realtime": snapshot.is_realtime,
                "provider_updated_at": snapshot.provider_updated_at.astimezone(UTC).isoformat(),
                "fetched_at": snapshot.fetched_at.astimezone(UTC).isoformat(),
                "data_source": snapshot.data_source,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        ex=50,
    )


class MassiveSnapshotApiMock:
    """HTTP-level Massive snapshot mock using the official full-market snapshot envelope."""

    def __init__(self, responses: list[dict[str, Any] | int]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, int):
            return httpx.Response(response, json={"status": "ERROR"})
        return httpx.Response(200, json=response)

    def client(self) -> MassiveSnapshotClient:
        return MassiveSnapshotClient(
            api_key="test-key",
            base_url="https://api.massive.com",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(self.handler),
                base_url="https://api.massive.com",
            ),
        )

    @property
    def requested_tickers(self) -> list[list[str]]:
        return [
            request.url.params.get("tickers", "").split(",")
            for request in self.requests
        ]


def _snapshot(ticker: str, *, data_source: str = "redis") -> Snapshot:
    return Snapshot(
        ticker=ticker,
        last=212.34,
        regular_close=212.00,
        change=1.23,
        change_pct=0.58,
        open=211.10,
        high=213.00,
        low=210.60,
        volume=45678901,
        prev_close=211.11,
        market_status="regular",
        session="regular",
        trading_day=date(2026, 4, 8),
        last_session="regular",
        last_trade_at=datetime(2026, 4, 8, 14, 30, tzinfo=UTC),
        delay_minutes=15,
        is_realtime=False,
        provider_updated_at=datetime(2026, 4, 8, 8, 30, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 8, 8, 31, tzinfo=UTC),
        data_source=data_source,
    )


def _massive_snapshot_payload(
    ticker: str,
    *,
    last: float = 212.34,
    regular_close: float = 212.0,
    change: float = 1.23,
    change_pct: float = 0.58,
    open_price: float = 211.10,
    high: float = 213.0,
    low: float = 210.60,
    volume: int = 45678901,
    prev_close: float = 211.11,
    last_trade_at_ms: int = 1775658600000,
    updated_ms: int = 1775658600000,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "todaysChange": change,
        "todaysChangePerc": change_pct,
        "updated": updated_ms,
        "day": {
            "o": open_price,
            "h": high,
            "l": low,
            "c": regular_close,
            "v": volume,
        },
        "min": {
            "c": last,
            "t": last_trade_at_ms,
        },
        "lastTrade": {
            "p": last,
            "t": last_trade_at_ms,
        },
        "prevDay": {
            "c": prev_close,
        },
    }


def _massive_snapshot_response(*tickers: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "OK",
        "count": len(tickers),
        "tickers": list(tickers),
    }


def _terminal_snapshot(ticker: str, *, data_source: str = "db_terminal_snapshot") -> Snapshot:
    return Snapshot(
        ticker=ticker,
        last=214.56,
        regular_close=212.00,
        change=2.56,
        change_pct=1.21,
        open=211.10,
        high=215.00,
        low=210.60,
        volume=55678901,
        prev_close=211.11,
        market_status="closed",
        session="closed",
        trading_day=date(2026, 4, 8),
        last_session="after_hours",
        last_trade_at=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
        delay_minutes=15,
        is_realtime=False,
        provider_updated_at=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 9, 0, 30, tzinfo=UTC),
        data_source=data_source,
    )


def _terminal_massive_snapshot_payload(ticker: str) -> dict[str, Any]:
    return _massive_snapshot_payload(
        ticker,
        last=214.56,
        regular_close=212.00,
        change=2.56,
        change_pct=1.21,
        open_price=211.10,
        high=215.00,
        low=210.60,
        volume=55678901,
        prev_close=211.11,
        last_trade_at_ms=1775692740000,
        updated_ms=1775692740000,
    )


def _seed_watchlist(session_factory, *, user_id: str, tickers: list[str]) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            for ticker in tickers:
                await repository.add(user_id=user_id, ticker=ticker)
            await session.commit()

    asyncio.run(seed())


def _seed_bars_1m(session_factory, bars: list[CanonicalBar]) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            repository = MarketBarRepository(session)
            await repository.upsert_1m(bars)
            await session.commit()

    asyncio.run(seed())


def _list_terminal_snapshots(
    session_factory,
    *,
    tickers: list[str],
    trading_day: date,
) -> list[Snapshot]:
    async def load() -> list[Snapshot]:
        async with session_factory() as session:
            repository = MarketTerminalSnapshotRepository(session)
            return await repository.list_for_tickers(tickers=tickers, trading_day=trading_day)

    return asyncio.run(load())


def _run_coordinator(
    integration_settings: Settings,
    *,
    snapshot_client: MassiveSnapshotClient,
):
    async def run():
        container = Container(
            integration_settings,
            snapshot_client=snapshot_client,
            now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
        )
        try:
            return await container.get_run_snapshot_coordinator_refresh_service().execute()
        finally:
            await container.shutdown()

    return asyncio.run(run())


def _run_terminal_finalizer(
    integration_settings: Settings,
    *,
    snapshot_client: MassiveSnapshotClient,
):
    async def run():
        container = Container(
            integration_settings,
            snapshot_client=snapshot_client,
            now_provider=lambda: datetime(2026, 4, 9, 0, 30, tzinfo=UTC),
        )
        try:
            return await container.get_run_terminal_snapshot_finalizer_service().execute()
        finally:
            await container.shutdown()

    return asyncio.run(run())


def _force_snapshot_query_active(client) -> None:
    client.app.state.container.set_market_data_now_provider(lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC))


def _force_snapshot_query_closed(client) -> None:
    client.app.state.container.set_market_data_now_provider(lambda: datetime(2026, 4, 9, 0, 30, tzinfo=UTC))


def test_market_data_capabilities_returns_resolved_mode(client) -> None:
    _, access_token = _register_and_authenticate(client, email="capabilities@example.com")

    response = client.get(
        "/api/v1/market-data/capabilities",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["market_data"] == {
        "delay_minutes": 15,
        "is_realtime": False,
        "supports_stream": False,
    }


def test_market_data_snapshots_rejects_unauthenticated_access(client) -> None:
    response = client.get("/api/v1/market-data/snapshots", params={"tickers": "AAPL"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
    assert response.json()["error"]["request_id"]


def test_market_data_snapshots_returns_cached_snapshot_on_redis_hit(client, redis_client) -> None:
    _force_snapshot_query_active(client)
    _, access_token = _register_and_authenticate(client, email="cache-hit@example.com")
    _seed_snapshot(redis_client, _snapshot("CACHEONLY"))

    response = client.get(
        "/api/v1/market-data/snapshots",
        params={"tickers": "CACHEONLY"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Request-ID": "reqcache01",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["ticker"] for item in payload["items"]] == ["CACHEONLY"]
    assert payload["items"][0]["last"] == 212.34
    assert payload["items"][0]["provider_updated_at"] == "2026-04-08T08:30:00Z"
    assert payload["meta"] == {
        "delay_minutes": 15,
        "is_realtime": False,
        "request_id": "reqcache01",
    }


def test_market_data_snapshots_falls_back_on_redis_miss_and_dedupes_input(
    redis_client,
    integration_settings: Settings,
) -> None:
    massive_api = MassiveSnapshotApiMock(
        [
            _massive_snapshot_response(
                _massive_snapshot_payload("AAPL"),
                _massive_snapshot_payload("MSFT"),
            )
        ]
    )
    app = create_app(
        integration_settings,
        snapshot_client=massive_api.client(),
        now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
    )

    with TestClient(app) as client:
        _, access_token = _register_and_authenticate(client, email="fallback@example.com")

        response = client.get(
            "/api/v1/market-data/snapshots",
            params={"tickers": "AAPL,AAPL,MSFT"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Request-ID": "reqmiss001",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    returned_tickers = [item["ticker"] for item in payload["items"]]
    assert returned_tickers == ["AAPL", "MSFT"]
    assert payload["meta"]["request_id"] == "reqmiss001"
    assert redis_client.exists("snapshot:AAPL") == 1
    assert redis_client.exists("snapshot:MSFT") == 1
    assert massive_api.requested_tickers == [["AAPL", "MSFT"]]
    assert massive_api.requests[0].url.path == "/v2/snapshot/locale/us/markets/stocks/tickers"


def test_market_data_snapshots_returns_resolved_subset_when_some_tickers_fail_upstream(
    integration_settings: Settings,
) -> None:
    custom_settings = integration_settings.model_copy(
        update={"market_data_snapshot_batch_size": 1}
    )
    massive_api = MassiveSnapshotApiMock(
        [
            _massive_snapshot_response(_massive_snapshot_payload("AAPL")),
            500,
        ]
    )
    app = create_app(
        custom_settings,
        snapshot_client=massive_api.client(),
        now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
    )

    with TestClient(app) as client:
        _, access_token = _register_and_authenticate(client, email="partial@example.com")

        response = client.get(
            "/api/v1/market-data/snapshots",
            params={"tickers": "AAPL,MSFT"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        returned_tickers = [item["ticker"] for item in payload["items"]]
        assert returned_tickers == ["AAPL"]
        assert massive_api.requested_tickers == [["AAPL"], ["MSFT"]]


def test_snapshot_coordinator_refreshes_unique_tickers_and_api_reads_results(
    client,
    session_factory,
    redis_client,
    integration_settings: Settings,
) -> None:
    _force_snapshot_query_active(client)
    first_user_id, first_token = _register_and_authenticate(client, email="coordinator1@example.com")
    second_user_id, _ = _register_and_authenticate(client, email="coordinator2@example.com")
    _seed_watchlist(session_factory, user_id=first_user_id, tickers=["AAPL", "MSFT"])
    _seed_watchlist(session_factory, user_id=second_user_id, tickers=["AAPL"])
    massive_api = MassiveSnapshotApiMock(
        [
            _massive_snapshot_response(
                _massive_snapshot_payload("AAPL"),
                _massive_snapshot_payload("MSFT"),
            )
        ]
    )

    result = _run_coordinator(integration_settings, snapshot_client=massive_api.client())

    assert result.status == "completed"
    assert result.total_tickers == 2
    assert result.failed_tickers == []
    assert redis_client.exists("snapshot:AAPL") == 1
    assert redis_client.exists("snapshot:MSFT") == 1
    assert massive_api.requested_tickers == [["AAPL", "MSFT"]]

    response = client.get(
        "/api/v1/market-data/snapshots",
        params={"tickers": "AAPL,MSFT"},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 200
    returned_tickers = [item["ticker"] for item in response.json()["items"]]
    assert returned_tickers == ["AAPL", "MSFT"]


def test_terminal_snapshot_finalizer_persists_rows_and_closed_api_reads_db(
    client,
    session_factory,
    integration_settings: Settings,
) -> None:
    _force_snapshot_query_closed(client)
    user_id, access_token = _register_and_authenticate(client, email="terminal-finalizer@example.com")
    _seed_watchlist(session_factory, user_id=user_id, tickers=["AAPL"])
    massive_api = MassiveSnapshotApiMock(
        [
            _massive_snapshot_response(_terminal_massive_snapshot_payload("AAPL"))
        ]
    )

    result = _run_terminal_finalizer(integration_settings, snapshot_client=massive_api.client())

    assert result.status == "completed"
    assert result.total_tickers == 1
    assert result.refreshed_tickers == 1
    assert result.failed_tickers == []
    assert massive_api.requested_tickers == [["AAPL"]]
    stored = _list_terminal_snapshots(
        session_factory,
        tickers=["AAPL"],
        trading_day=date(2026, 4, 8),
    )
    assert len(stored) == 1
    assert stored[0].last == 214.56
    assert stored[0].session == "closed"
    assert stored[0].last_session == "after_hours"

    response = client.get(
        "/api/v1/market-data/snapshots",
        params={"tickers": "AAPL"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["ticker"] == "AAPL"
    assert payload["items"][0]["last"] == 214.56
    assert payload["items"][0]["session"] == "closed"
    assert payload["items"][0]["trading_day"] == "2026-04-08"
    assert massive_api.requested_tickers == [["AAPL"]]


def test_closed_snapshot_api_falls_back_for_terminal_miss_and_upserts_only_requested_tickers(
    integration_settings: Settings,
    session_factory,
    redis_client,
) -> None:
    massive_api = MassiveSnapshotApiMock(
        [
            _massive_snapshot_response(_terminal_massive_snapshot_payload("MSFT"))
        ]
    )
    app = create_app(
        integration_settings,
        snapshot_client=massive_api.client(),
        now_provider=lambda: datetime(2026, 4, 9, 0, 30, tzinfo=UTC),
    )

    with TestClient(app) as client:
        _, access_token = _register_and_authenticate(client, email="terminal-fallback@example.com")

        response = client.get(
            "/api/v1/market-data/snapshots",
            params={"tickers": "MSFT"},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["ticker"] for item in payload["items"]] == ["MSFT"]
    assert payload["items"][0]["session"] == "closed"
    assert payload["items"][0]["trading_day"] == "2026-04-08"
    assert massive_api.requested_tickers == [["MSFT"]]
    stored = _list_terminal_snapshots(
        session_factory,
        tickers=["MSFT", "TSLA"],
        trading_day=date(2026, 4, 8),
    )
    assert [snapshot.ticker for snapshot in stored] == ["MSFT"]
    assert stored[0].data_source == "massive_terminal_snapshot_fallback"
    assert redis_client.exists("snapshot:MSFT") == 0


def test_market_data_bars_returns_seeded_intraday_bars_with_headers(client, session_factory) -> None:
    _, access_token = _register_and_authenticate(client, email="bars@example.com")
    _seed_bars_1m(
        session_factory,
        bars=[
            CanonicalBar(
                ticker="AAPL",
                adjustment="split_adjusted",
                granularity="1m",
                bucket_start_at=datetime(2026, 4, 15, 13, 30, tzinfo=UTC),
                trading_day=datetime(2026, 4, 15, 13, 30, tzinfo=UTC).date(),
                session_kind="regular",
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=10,
                vw=100.4,
                trade_count=2,
                provider_updated_at=datetime(2026, 4, 15, 13, 30, tzinfo=UTC),
                is_final=True,
                first_synced_at=datetime(2026, 4, 15, 13, 31, tzinfo=UTC),
                last_synced_at=datetime(2026, 4, 15, 13, 31, tzinfo=UTC),
            )
        ],
    )

    response = client.get(
        "/api/v1/market-data/bars",
        params={
            "ticker": "AAPL",
            "resolution": "1m",
            "session": "regular",
            "from": "2026-04-15T13:30:00Z",
            "to": "2026-04-15T13:31:00Z",
            "fill": "none",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bars"][0]["time"] == "2026-04-15T13:30:00Z"
    assert payload["bars"][0]["close"] == 100.5
    assert payload["meta"]["ticker"] == "AAPL"
    assert payload["meta"]["readiness"] == "ready"
    assert response.headers["X-Data-Source"] == "db"
    assert response.headers["X-Partial-Range"] == "false"
