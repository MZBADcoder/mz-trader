"""Integration tests for market-data routes with real app wiring."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from application.container import Container
from domain.entities import CanonicalBar, Snapshot
from domain.exceptions import MarketSnapshotUpstreamUnavailableError
from infrastructure.external import MassiveSnapshotBatchResponse, MassiveSnapshotClient
from infrastructure.repositories.market_bar_repository import MarketBarRepository
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


class ScriptedSnapshotClient(MassiveSnapshotClient):
    def __init__(self, responses: list[MassiveSnapshotBatchResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[list[str], str]] = []

    async def close(self) -> None:
        return None

    async def fetch_snapshots(
        self,
        *,
        tickers: list[str],
        mode,
        data_source: str,
    ) -> MassiveSnapshotBatchResponse:
        self.calls.append((list(tickers), data_source))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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


def _force_snapshot_query_active(client) -> None:
    client.app.state.container.set_market_data_now_provider(lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC))


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
    snapshot_client = ScriptedSnapshotClient(
        [
            MassiveSnapshotBatchResponse(
                snapshots=[
                    _snapshot("AAPL", data_source="massive_fallback"),
                    _snapshot("MSFT", data_source="massive_fallback"),
                ],
                unresolved_tickers=[],
            )
        ]
    )
    app = create_app(
        integration_settings,
        snapshot_client=snapshot_client,
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
    assert snapshot_client.calls == [(["AAPL", "MSFT"], "massive_fallback")]


def test_market_data_snapshots_returns_resolved_subset_when_some_tickers_fail_upstream(
    integration_settings: Settings,
) -> None:
    custom_settings = integration_settings.model_copy(
        update={"market_data_snapshot_batch_size": 1}
    )
    snapshot_client = ScriptedSnapshotClient(
        [
            MassiveSnapshotBatchResponse(
                snapshots=[_snapshot("AAPL", data_source="massive_fallback")],
                unresolved_tickers=[],
            ),
            MarketSnapshotUpstreamUnavailableError(detail="Snapshot provider request failed."),
        ]
    )
    app = create_app(
        custom_settings,
        snapshot_client=snapshot_client,
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
        assert snapshot_client.calls == [
            (["AAPL"], "massive_fallback"),
            (["MSFT"], "massive_fallback"),
        ]


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
    snapshot_client = ScriptedSnapshotClient(
        [
            MassiveSnapshotBatchResponse(
                snapshots=[
                    _snapshot("AAPL", data_source="massive_coordinator"),
                    _snapshot("MSFT", data_source="massive_coordinator"),
                ],
                unresolved_tickers=[],
            )
        ]
    )

    result = _run_coordinator(integration_settings, snapshot_client=snapshot_client)

    assert result.status == "completed"
    assert result.total_tickers == 2
    assert result.failed_tickers == []
    assert redis_client.exists("snapshot:AAPL") == 1
    assert redis_client.exists("snapshot:MSFT") == 1
    assert snapshot_client.calls == [(["AAPL", "MSFT"], "massive_coordinator")]

    response = client.get(
        "/api/v1/market-data/snapshots",
        params={"tickers": "AAPL,MSFT"},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 200
    returned_tickers = [item["ticker"] for item in response.json()["items"]]
    assert returned_tickers == ["AAPL", "MSFT"]


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
