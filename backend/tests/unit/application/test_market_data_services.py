"""Market data service tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from application.services.market_data import GetBatchSnapshotsService, RunSnapshotCoordinatorRefreshService
from domain.entities import MarketDataMode, Snapshot
from domain.exceptions import MarketSnapshotUpstreamUnavailableError
from infrastructure.external import MassiveSnapshotBatchResponse


def _snapshot(ticker: str, *, data_source: str = "redis") -> Snapshot:
    return Snapshot(
        ticker=ticker,
        last=212.34,
        change=1.23,
        change_pct=0.58,
        open=211.10,
        high=213.00,
        low=210.60,
        volume=45678901,
        prev_close=211.11,
        market_status="regular",
        delay_minutes=15,
        is_realtime=False,
        provider_updated_at=datetime(2026, 4, 8, 8, 30, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 8, 8, 31, tzinfo=UTC),
        data_source=data_source,
    )


class FakeSnapshotStore:
    def __init__(self, cached: dict[str, Snapshot] | None = None, *, lock_token: str | None = "lock-1") -> None:
        self.cached = cached or {}
        self.saved_batches: list[list[Snapshot]] = []
        self.lock_token = lock_token
        self.acquire_calls: list[int] = []
        self.release_tokens: list[str] = []

    async def get_many(self, tickers: list[str]) -> dict[str, Snapshot]:
        return {ticker: self.cached[ticker] for ticker in tickers if ticker in self.cached}

    async def set_many(self, snapshots: list[Snapshot]) -> None:
        self.saved_batches.append(list(snapshots))

    async def acquire_refresh_lock(self, *, ttl_seconds: int) -> str | None:
        self.acquire_calls.append(ttl_seconds)
        return self.lock_token

    async def release_refresh_lock(self, token: str) -> bool:
        self.release_tokens.append(token)
        return True


class FakeSnapshotClient:
    def __init__(
        self,
        *,
        responses: list[MassiveSnapshotBatchResponse] | None = None,
        raises: set[tuple[str, ...]] | None = None,
    ) -> None:
        self.responses = responses or []
        self.raises = raises or set()
        self.calls: list[tuple[list[str], str]] = []

    async def fetch_snapshots(
        self,
        *,
        tickers: list[str],
        mode: MarketDataMode,
        data_source: str,
    ) -> MassiveSnapshotBatchResponse:
        self.calls.append((list(tickers), data_source))
        if tuple(tickers) in self.raises:
            raise MarketSnapshotUpstreamUnavailableError(detail="Snapshot provider request failed.")
        return self.responses.pop(0)


class FakeWatchlistRepository:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers

    async def list_distinct_tickers(self) -> list[str]:
        return list(self._tickers)


class FakeUow:
    def __init__(self, tickers: list[str]) -> None:
        self.watchlist = FakeWatchlistRepository(tickers)

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeUowFactory:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers

    def build(self) -> FakeUow:
        return FakeUow(self._tickers)


def test_get_batch_snapshots_service_reads_cache_then_fetches_only_missing_tickers() -> None:
    store = FakeSnapshotStore(cached={"AAPL": _snapshot("AAPL", data_source="redis")})
    client = FakeSnapshotClient(
        responses=[
            MassiveSnapshotBatchResponse(
                snapshots=[_snapshot("MSFT", data_source="massive_fallback")],
                unresolved_tickers=["NVDA"],
            )
        ]
    )
    service = GetBatchSnapshotsService(
        snapshot_store=store,
        snapshot_client=client,
        mode=MarketDataMode(delay_minutes=15),
        request_limit=50,
        batch_size=10,
    )

    result = asyncio.run(service.execute(user_id="user-1", tickers=["AAPL", "NVDA", "MSFT"]))

    assert [item.ticker for item in result.items] == ["AAPL", "MSFT"]
    assert client.calls == [(["NVDA", "MSFT"], "massive_fallback")]
    assert store.saved_batches == [[_snapshot("MSFT", data_source="massive_fallback")]]
    assert result.delay_minutes == 15
    assert result.is_realtime is False


def test_get_batch_snapshots_service_raises_when_everything_is_unresolved() -> None:
    store = FakeSnapshotStore()
    client = FakeSnapshotClient(
        responses=[MassiveSnapshotBatchResponse(snapshots=[], unresolved_tickers=["AAPL", "MSFT"])]
    )
    service = GetBatchSnapshotsService(
        snapshot_store=store,
        snapshot_client=client,
        mode=MarketDataMode(delay_minutes=15),
        request_limit=50,
        batch_size=10,
    )

    with pytest.raises(MarketSnapshotUpstreamUnavailableError):
        asyncio.run(service.execute(user_id="user-1", tickers=["AAPL", "MSFT"]))


def test_run_snapshot_coordinator_refresh_service_skips_when_lock_not_acquired() -> None:
    store = FakeSnapshotStore(lock_token=None)
    client = FakeSnapshotClient()
    service = RunSnapshotCoordinatorRefreshService(
        uow_factory=FakeUowFactory(["AAPL", "MSFT"]),
        snapshot_store=store,
        snapshot_client=client,
        mode=MarketDataMode(delay_minutes=15),
        batch_size=100,
        refresh_lock_ttl_seconds=25,
    )

    result = asyncio.run(service.execute())

    assert result.status == "skipped"
    assert result.skip_reason == "lock_not_acquired"
    assert result.total_tickers == 0
    assert client.calls == []
    assert store.acquire_calls == [25]
    assert store.release_tokens == []


def test_run_snapshot_coordinator_refresh_service_batches_and_releases_lock() -> None:
    store = FakeSnapshotStore(lock_token="lock-1")
    client = FakeSnapshotClient(
        responses=[
            MassiveSnapshotBatchResponse(
                snapshots=[_snapshot("AAPL", data_source="massive_coordinator")],
                unresolved_tickers=["MSFT"],
            ),
            MassiveSnapshotBatchResponse(
                snapshots=[_snapshot("NVDA", data_source="massive_coordinator")],
                unresolved_tickers=[],
            ),
        ]
    )
    service = RunSnapshotCoordinatorRefreshService(
        uow_factory=FakeUowFactory(["AAPL", "MSFT", "NVDA"]),
        snapshot_store=store,
        snapshot_client=client,
        mode=MarketDataMode(delay_minutes=15),
        batch_size=2,
        refresh_lock_ttl_seconds=25,
    )

    result = asyncio.run(service.execute())

    assert result.status == "completed"
    assert result.total_tickers == 3
    assert result.refreshed_tickers == 2
    assert result.failed_tickers == ["MSFT"]
    assert result.skip_reason is None
    assert client.calls == [
        (["AAPL", "MSFT"], "massive_coordinator"),
        (["NVDA"], "massive_coordinator"),
    ]
    assert store.saved_batches == [
        [_snapshot("AAPL", data_source="massive_coordinator")],
        [_snapshot("NVDA", data_source="massive_coordinator")],
    ]
    assert store.release_tokens == ["lock-1"]
