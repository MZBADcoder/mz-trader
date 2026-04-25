"""Market data service tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest

from application.services.market_data import (
    GetBatchSnapshotsService,
    RunSnapshotCoordinatorRefreshService,
    RunTerminalSnapshotFinalizerService,
)
from domain.entities import MarketDataMode, Snapshot
from domain.exceptions import MarketSnapshotUpstreamUnavailableError
from infrastructure.calendar import UsStockCalendar
from infrastructure.external import MassiveSnapshotBatchResponse


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
    def __init__(self, tickers: list[str], terminal_snapshots: list[Snapshot] | None = None) -> None:
        self.watchlist = FakeWatchlistRepository(tickers)
        self.terminal_snapshots = FakeTerminalSnapshotRepository(
            terminal_snapshots if terminal_snapshots is not None else []
        )

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None


class FakeUowFactory:
    def __init__(self, tickers: list[str], terminal_snapshots: list[Snapshot] | None = None) -> None:
        self._tickers = tickers
        self._terminal_snapshots = terminal_snapshots if terminal_snapshots is not None else []

    def build(self) -> FakeUow:
        return FakeUow(self._tickers, self._terminal_snapshots)


class FakeTerminalSnapshotRepository:
    def __init__(self, snapshots: list[Snapshot]) -> None:
        self._snapshots = snapshots

    async def list_for_tickers(self, *, tickers: list[str], trading_day: date) -> list[Snapshot]:
        ticker_set = set(tickers)
        return [
            snapshot
            for snapshot in self._snapshots
            if snapshot.ticker in ticker_set and snapshot.trading_day == trading_day
        ]

    async def upsert_many(self, *, snapshots: list[Snapshot], captured_at: datetime) -> None:
        self._snapshots.extend(snapshots)


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
        uow_factory=FakeUowFactory([]),
        snapshot_store=store,
        snapshot_client=client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        request_limit=50,
        batch_size=10,
        now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
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
        uow_factory=FakeUowFactory([]),
        snapshot_store=store,
        snapshot_client=client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        request_limit=50,
        batch_size=10,
        now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
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
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        batch_size=100,
        refresh_lock_ttl_seconds=25,
        now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
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
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        batch_size=2,
        refresh_lock_ttl_seconds=25,
        now_provider=lambda: datetime(2026, 4, 8, 15, 0, tzinfo=UTC),
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


def test_run_snapshot_coordinator_refresh_service_skips_outside_trading_window() -> None:
    store = FakeSnapshotStore(lock_token="lock-1")
    client = FakeSnapshotClient()
    service = RunSnapshotCoordinatorRefreshService(
        uow_factory=FakeUowFactory(["AAPL"]),
        snapshot_store=store,
        snapshot_client=client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        batch_size=100,
        refresh_lock_ttl_seconds=25,
        now_provider=lambda: datetime(2026, 4, 8, 2, 0, tzinfo=UTC),
    )

    result = asyncio.run(service.execute())

    assert result.status == "skipped"
    assert result.skip_reason == "outside_snapshot_refresh_window"
    assert store.acquire_calls == []
    assert client.calls == []


def test_get_batch_snapshots_service_reads_terminal_snapshots_when_closed() -> None:
    terminal_snapshot = _snapshot("AAPL", data_source="db_terminal_snapshot")
    store = FakeSnapshotStore()
    client = FakeSnapshotClient()
    service = GetBatchSnapshotsService(
        uow_factory=FakeUowFactory([], terminal_snapshots=[terminal_snapshot]),
        snapshot_store=store,
        snapshot_client=client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        request_limit=50,
        batch_size=10,
        now_provider=lambda: datetime(2026, 4, 9, 2, 0, tzinfo=UTC),
    )

    result = asyncio.run(service.execute(user_id="user-1", tickers=["AAPL"]))

    assert [item.ticker for item in result.items] == ["AAPL"]
    assert result.items[0].session == "closed"
    assert client.calls == []
    assert store.saved_batches == []


def test_run_terminal_snapshot_finalizer_persists_after_hours_terminal_snapshots() -> None:
    uow_factory = FakeUowFactory(["AAPL"])
    client = FakeSnapshotClient(
        responses=[
            MassiveSnapshotBatchResponse(
                snapshots=[_snapshot("AAPL", data_source="massive_terminal_snapshot_finalizer")],
                unresolved_tickers=[],
            )
        ]
    )
    service = RunTerminalSnapshotFinalizerService(
        uow_factory=uow_factory,
        snapshot_client=client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=15),
        batch_size=100,
        now_provider=lambda: datetime(2026, 4, 9, 0, 30, tzinfo=UTC),
    )

    result = asyncio.run(service.execute())

    assert result.status == "completed"
    assert result.refreshed_tickers == 1
    assert client.calls == [(["AAPL"], "massive_terminal_snapshot_finalizer")]
    stored = uow_factory._terminal_snapshots
    assert len(stored) == 1
    assert stored[0].trading_day == date(2026, 4, 8)
    assert stored[0].session == "closed"
