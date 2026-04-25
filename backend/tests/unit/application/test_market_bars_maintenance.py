"""Tests for bars maintenance state helpers and retention cleanup."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import cast

from application.services.market_data._bars_maintenance_support import (
    build_ready_state,
    clamp_state_to_retention,
    retain_latest_extended_session_rows,
)
from application.services.market_data.run_historical_bars_gap_reconciliation import (
    RunHistoricalBarsGapReconciliationService,
)
from application.services.market_data.run_bars_retention_cleanup import RunBarsRetentionCleanupService
from application.services.market_data.run_post_close_bars_finalizer import RunPostCloseBarsFinalizerService
from application.services.market_data.run_ticker_bars_bootstrap import RunTickerBarsBootstrapService
from domain.entities import CanonicalBar, MarketDataMode, ProviderBar, TickerBarsState
from domain.rules import MARKET_BARS_1M_RETENTION_TRADING_DAYS
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _state(**overrides) -> TickerBarsState:
    baseline = TickerBarsState(
        ticker="AAPL",
        status="ready",
        bootstrap_requested_at=_dt(2026, 4, 1, 13, 30),
        bootstrap_started_at=_dt(2026, 4, 1, 13, 31),
        bootstrap_finished_at=_dt(2026, 4, 1, 13, 40),
        bootstrap_failed_at=None,
        last_reconciled_at=_dt(2026, 4, 15, 20, 0),
        earliest_1m_trading_day=date(2026, 4, 1),
        last_1m_trading_day=date(2026, 4, 15),
        last_1m_bucket_start_at=_dt(2026, 4, 15, 19, 59),
        earliest_1d_trading_day=date(2026, 1, 2),
        latest_1d_trading_day=date(2026, 4, 15),
        last_error_code=None,
        last_error_message=None,
        created_at=_dt(2026, 4, 1, 13, 30),
        updated_at=_dt(2026, 4, 15, 20, 0),
    )
    for key, value in overrides.items():
        setattr(baseline, key, value)
    return baseline


def _canonical_1m(
    *,
    trading_day: date,
    bucket_start_at: datetime,
    session_kind: str = "regular",
) -> CanonicalBar:
    return CanonicalBar(
        ticker="AAPL",
        adjustment="split_adjusted",
        granularity="1m",
        bucket_start_at=bucket_start_at,
        trading_day=trading_day,
        session_kind=session_kind,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10,
        vw=100.4,
        trade_count=2,
        provider_updated_at=bucket_start_at,
        is_final=True,
        first_synced_at=bucket_start_at,
        last_synced_at=bucket_start_at,
    )


def _canonical_1d(*, trading_day: date, bucket_start_at: datetime) -> CanonicalBar:
    return CanonicalBar(
        ticker="AAPL",
        adjustment="split_adjusted",
        granularity="1d",
        bucket_start_at=bucket_start_at,
        trading_day=trading_day,
        session_kind="regular",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10,
        vw=100.4,
        trade_count=2,
        provider_updated_at=bucket_start_at,
        is_final=True,
        first_synced_at=bucket_start_at,
        last_synced_at=bucket_start_at,
    )


def _historical_reconciliation_minute_rows(
    *,
    calendar: UsStockCalendar,
    anchor_day: date,
    effective_now: datetime,
    omit: set[datetime] | None = None,
) -> list[CanonicalBar]:
    omitted = omit or set()
    rows: list[CanonicalBar] = []
    for day in calendar.previous_trading_days(anchor_day, MARKET_BARS_1M_RETENTION_TRADING_DAYS):
        window = calendar.regular_session_window(day)
        current = window.start_at
        end_at = min(window.end_at, effective_now)
        while current + timedelta(minutes=1) <= end_at:
            if current not in omitted:
                trading_day, session_kind = calendar.classify_session(current)
                assert session_kind == "regular"
                rows.append(
                    _canonical_1m(
                        trading_day=trading_day,
                        bucket_start_at=current,
                        session_kind=session_kind,
                    )
                )
            current += timedelta(minutes=1)
    return rows


def _historical_reconciliation_daily_rows(
    *,
    calendar: UsStockCalendar,
    anchor_day: date,
    effective_now: datetime,
) -> list[CanonicalBar]:
    completed_end_day = anchor_day
    market_day = calendar.to_market_date(effective_now)
    if calendar.is_trading_day(market_day) and anchor_day == market_day:
        completed_end_day = calendar.previous_trading_day(anchor_day)
    start_day = calendar.previous_trading_days(anchor_day, 90)[0]
    return [
        _canonical_1d(trading_day=day, bucket_start_at=calendar.regular_session_window(day).start_at)
        for day in calendar.trading_days_between(start_day, completed_end_day)
    ]


def test_build_ready_state_preserves_existing_earliest_bounds_on_incremental_updates() -> None:
    existing = _state()
    now = _dt(2026, 4, 20, 20, 0)

    updated = build_ready_state(
        ticker="AAPL",
        now=now,
        minute_rows=[_canonical_1m(trading_day=date(2026, 4, 20), bucket_start_at=_dt(2026, 4, 20, 19, 59))],
        daily_rows=[_canonical_1d(trading_day=date(2026, 4, 20), bucket_start_at=_dt(2026, 4, 20, 13, 30))],
        existing=existing,
    )

    assert updated.earliest_1m_trading_day == date(2026, 4, 1)
    assert updated.last_1m_trading_day == date(2026, 4, 20)
    assert updated.last_1m_bucket_start_at == _dt(2026, 4, 20, 19, 59)
    assert updated.earliest_1d_trading_day == date(2026, 1, 2)
    assert updated.latest_1d_trading_day == date(2026, 4, 20)


def test_clamp_state_to_retention_advances_or_clears_stale_bounds() -> None:
    now = _dt(2026, 4, 21, 0, 0)
    retained = clamp_state_to_retention(
        state=_state(),
        minute_threshold_day=date(2026, 4, 10),
        daily_threshold_day=date(2026, 4, 1),
        now=now,
    )
    expired = clamp_state_to_retention(
        state=_state(
            ticker="MSFT",
            earliest_1m_trading_day=date(2026, 3, 1),
            last_1m_trading_day=date(2026, 3, 7),
            last_1m_bucket_start_at=_dt(2026, 3, 7, 19, 59),
            earliest_1d_trading_day=date(2025, 3, 1),
            latest_1d_trading_day=date(2025, 3, 7),
        ),
        minute_threshold_day=date(2026, 4, 10),
        daily_threshold_day=date(2026, 4, 1),
        now=now,
    )

    assert retained.earliest_1m_trading_day == date(2026, 4, 10)
    assert retained.last_1m_trading_day == date(2026, 4, 15)
    assert retained.earliest_1d_trading_day == date(2026, 4, 1)
    assert retained.latest_1d_trading_day == date(2026, 4, 15)
    assert expired.earliest_1m_trading_day is None
    assert expired.last_1m_trading_day is None
    assert expired.last_1m_bucket_start_at is None
    assert expired.earliest_1d_trading_day is None
    assert expired.latest_1d_trading_day is None


def test_retain_latest_extended_session_rows_keeps_historical_regular_only() -> None:
    rows = [
        _canonical_1m(
            trading_day=date(2026, 4, 20),
            bucket_start_at=_dt(2026, 4, 20, 12, 0),
            session_kind="pre_market",
        ),
        _canonical_1m(
            trading_day=date(2026, 4, 20),
            bucket_start_at=_dt(2026, 4, 20, 14, 0),
            session_kind="regular",
        ),
        _canonical_1m(
            trading_day=date(2026, 4, 20),
            bucket_start_at=_dt(2026, 4, 20, 21, 0),
            session_kind="after_hours",
        ),
        _canonical_1m(
            trading_day=date(2026, 4, 21),
            bucket_start_at=_dt(2026, 4, 21, 12, 0),
            session_kind="pre_market",
        ),
        _canonical_1m(
            trading_day=date(2026, 4, 21),
            bucket_start_at=_dt(2026, 4, 21, 14, 0),
            session_kind="regular",
        ),
    ]

    retained = retain_latest_extended_session_rows(
        rows=rows,
        latest_extended_trading_day=date(2026, 4, 21),
    )

    assert [(row.trading_day, row.session_kind) for row in retained] == [
        (date(2026, 4, 20), "regular"),
        (date(2026, 4, 21), "pre_market"),
        (date(2026, 4, 21), "regular"),
    ]


class FakeBarsRepository:
    def __init__(self) -> None:
        self.deleted_1m_calls: list[tuple[date, list[str] | None]] = []
        self.deleted_1d_threshold: date | None = None
        self.minute_rows: list[CanonicalBar] = []
        self.daily_rows: list[CanonicalBar] = []
        self.upserted_1m: list[CanonicalBar] = []
        self.upserted_1d: list[CanonicalBar] = []

    async def list_1m(self, *, ticker, adjustment, start_at, end_at, session_kind=None):
        return [
            row
            for row in self.minute_rows
            if row.ticker == ticker
            and row.adjustment == adjustment
            and start_at <= row.bucket_start_at < end_at
            and (session_kind is None or row.session_kind == session_kind)
        ]

    async def list_1d(self, *, ticker, adjustment, start_day, end_day):
        return [
            row
            for row in self.daily_rows
            if row.ticker == ticker
            and row.adjustment == adjustment
            and start_day <= row.trading_day <= end_day
        ]

    async def upsert_1m(self, bars: list[CanonicalBar]) -> None:
        self.upserted_1m.extend(bars)

    async def upsert_1d(self, bars: list[CanonicalBar]) -> None:
        self.upserted_1d.extend(bars)

    async def delete_1m_before(
        self,
        *,
        threshold_day: date,
        session_kinds: list[str] | None = None,
    ) -> int:
        self.deleted_1m_calls.append((threshold_day, session_kinds))
        return 12 if session_kinds is None else 4

    async def delete_1d_before(self, *, threshold_day: date) -> int:
        self.deleted_1d_threshold = threshold_day
        return 3


class FakeTickerBarsStateRepository:
    def __init__(self, states: list[TickerBarsState]) -> None:
        self._states = states
        self.upserted: list[TickerBarsState] = []
        self.failed_tickers: list[str] = []

    async def list_by_statuses(self, *, statuses: list[str]) -> list[TickerBarsState]:
        return [state for state in self._states if state.status in statuses]

    async def list_for_tickers(self, *, tickers: list[str]) -> list[TickerBarsState]:
        ticker_set = set(tickers)
        return [state for state in self._states if state.ticker in ticker_set]

    async def get_for_update(self, *, ticker: str) -> TickerBarsState | None:
        for state in self._states:
            if state.ticker == ticker:
                return state
        return None

    async def upsert(self, state: TickerBarsState) -> None:
        self.upserted.append(state)

    async def mark_failed(self, *, ticker: str, failed_at: datetime, error_message: str) -> None:
        self.failed_tickers.append(ticker)
        state = await self.get_for_update(ticker=ticker)
        if state is None:
            return
        state.status = "failed"
        state.bootstrap_failed_at = failed_at
        state.last_error_code = "bootstrap_failed"
        state.last_error_message = error_message
        state.updated_at = failed_at


class FakeWatchlistRepository:
    def __init__(self, tickers: list[str]) -> None:
        self._tickers = tickers

    async def list_distinct_tickers(self) -> list[str]:
        return self._tickers


class FakeUow:
    def __init__(
        self,
        bars: FakeBarsRepository,
        state_repository: FakeTickerBarsStateRepository,
        watchlist: FakeWatchlistRepository | None = None,
    ) -> None:
        self.bars = bars
        self.ticker_bars_state = state_repository
        self.watchlist = watchlist or FakeWatchlistRepository([])
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeUowFactory:
    def __init__(self, uow: FakeUow) -> None:
        self._uow = uow

    def build(self) -> FakeUow:
        return self._uow


class FakeBarsClient:
    def __init__(self) -> None:
        self.fetch_calls = 0
        self.calls: list[dict] = []
        self.responses: list[list[ProviderBar]] = []

    async def fetch_range(self, **kwargs):
        self.fetch_calls += 1
        self.calls.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return []


class FakeBootstrapService:
    def __init__(self) -> None:
        self.tickers: list[str] | None = None

    async def execute(self, *, tickers: list[str] | None = None):
        self.tickers = tickers
        return type(
            "BootstrapResult",
            (),
            {"refreshed_tickers": len(tickers or []), "failed_tickers": []},
        )()


def test_bootstrap_scan_skips_initializing_tickers() -> None:
    bars = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository([
        _state(status="initializing", bootstrap_started_at=_dt(2026, 4, 21, 19, 55))
    ])
    uow = FakeUow(bars, state_repository)
    bars_client = FakeBarsClient()
    service = RunTickerBarsBootstrapService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        bars_client=cast(MassiveBarsClient, bars_client),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 21, 20, 0),
    )

    result = asyncio.run(service.execute())

    assert result.total_tickers == 0
    assert result.refreshed_tickers == 0
    assert state_repository.failed_tickers == []
    assert bars_client.fetch_calls == 0


def test_bootstrap_scan_marks_timed_out_initializing_failed_before_retry() -> None:
    bars = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository([
        _state(status="initializing", bootstrap_started_at=_dt(2026, 4, 21, 19, 45))
    ])
    uow = FakeUow(bars, state_repository)
    bars_client = FakeBarsClient()
    service = RunTickerBarsBootstrapService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        bars_client=cast(MassiveBarsClient, bars_client),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 21, 20, 0),
    )

    result = asyncio.run(service.execute())

    assert result.total_tickers == 1
    assert result.refreshed_tickers == 1
    assert state_repository.failed_tickers == ["AAPL"]
    assert bars_client.fetch_calls == 2


def test_historical_reconciliation_only_bootstraps_timed_out_initializing_tickers() -> None:
    bars = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository(
        [
            _state(ticker="AAPL", status="initializing", bootstrap_started_at=_dt(2026, 4, 21, 19, 55)),
            _state(ticker="MSFT", status="initializing", bootstrap_started_at=_dt(2026, 4, 21, 19, 45)),
        ]
    )
    uow = FakeUow(bars, state_repository, FakeWatchlistRepository(["AAPL", "MSFT"]))
    bars_client = FakeBarsClient()
    bootstrap_service = FakeBootstrapService()
    service = RunHistoricalBarsGapReconciliationService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        bars_client=cast(MassiveBarsClient, bars_client),
        calendar=UsStockCalendar(),
        bootstrap_service=cast(RunTickerBarsBootstrapService, bootstrap_service),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 21, 20, 0),
    )

    result = asyncio.run(service.execute())

    assert bootstrap_service.tickers == ["MSFT"]
    assert bars_client.fetch_calls == 0
    assert result.processed_tickers == 1


def test_historical_reconciliation_skips_provider_when_no_gaps_exist() -> None:
    bars = FakeBarsRepository()
    calendar = UsStockCalendar()
    trading_day = date(2026, 4, 21)
    regular = calendar.regular_session_window(trading_day)
    effective_now = regular.start_at + timedelta(minutes=2)
    bars.minute_rows = _historical_reconciliation_minute_rows(
        calendar=calendar,
        anchor_day=trading_day,
        effective_now=effective_now,
    )
    bars.daily_rows = _historical_reconciliation_daily_rows(
        calendar=calendar,
        anchor_day=trading_day,
        effective_now=effective_now,
    )
    state_repository = FakeTickerBarsStateRepository([_state()])
    uow = FakeUow(bars, state_repository, FakeWatchlistRepository(["AAPL"]))
    bars_client = FakeBarsClient()
    bootstrap_service = FakeBootstrapService()
    service = RunHistoricalBarsGapReconciliationService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        bars_client=cast(MassiveBarsClient, bars_client),
        calendar=calendar,
        bootstrap_service=cast(RunTickerBarsBootstrapService, bootstrap_service),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: effective_now,
    )

    result = asyncio.run(service.execute())

    assert result.processed_tickers == 1
    assert bars_client.fetch_calls == 0
    assert bars.upserted_1m == []
    assert bars.upserted_1d == []


def test_historical_reconciliation_fetches_only_missing_minute_gap() -> None:
    bars = FakeBarsRepository()
    calendar = UsStockCalendar()
    trading_day = date(2026, 4, 21)
    regular = calendar.regular_session_window(trading_day)
    effective_now = regular.start_at + timedelta(minutes=3)
    missing_start = regular.start_at + timedelta(minutes=1)
    bars.minute_rows = _historical_reconciliation_minute_rows(
        calendar=calendar,
        anchor_day=trading_day,
        effective_now=effective_now,
        omit={missing_start},
    )
    bars.daily_rows = _historical_reconciliation_daily_rows(
        calendar=calendar,
        anchor_day=trading_day,
        effective_now=effective_now,
    )
    state_repository = FakeTickerBarsStateRepository([_state()])
    uow = FakeUow(bars, state_repository, FakeWatchlistRepository(["AAPL"]))
    bars_client = FakeBarsClient()
    bars_client.responses = [
        [
            ProviderBar(
                time=missing_start,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10,
                vw=100.4,
                trade_count=2,
                provider_updated_at=missing_start,
            )
        ]
    ]
    bootstrap_service = FakeBootstrapService()
    service = RunHistoricalBarsGapReconciliationService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        bars_client=cast(MassiveBarsClient, bars_client),
        calendar=calendar,
        bootstrap_service=cast(RunTickerBarsBootstrapService, bootstrap_service),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: effective_now,
    )

    result = asyncio.run(service.execute())

    assert result.processed_tickers == 1
    assert bars_client.fetch_calls == 1
    assert bars_client.calls[0]["timespan"] == "minute"
    assert bars_client.calls[0]["from_value"] == str(int(missing_start.timestamp() * 1000))
    assert bars_client.calls[0]["to_value"] == str(int((missing_start + timedelta(minutes=1)).timestamp() * 1000))
    assert [row.bucket_start_at for row in bars.upserted_1m] == [missing_start]
    assert bars.upserted_1d == []


def test_post_close_finalizer_skips_initializing_tickers() -> None:
    bars = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository([
        _state(status="initializing", bootstrap_started_at=_dt(2026, 4, 21, 20, 55))
    ])
    uow = FakeUow(bars, state_repository, FakeWatchlistRepository(["AAPL"]))
    bars_client = FakeBarsClient()
    service = RunPostCloseBarsFinalizerService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        bars_client=cast(MassiveBarsClient, bars_client),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 21, 21, 0),
    )

    result = asyncio.run(service.execute())

    assert result.total_tickers == 1
    assert result.refreshed_tickers == 0
    assert bars_client.fetch_calls == 0


def test_retention_cleanup_updates_state_bounds_after_deleting_old_rows() -> None:
    bars = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository([_state()])
    uow = FakeUow(bars, state_repository)
    service = RunBarsRetentionCleanupService(
        uow_factory=cast(SqlAlchemyUnitOfWorkFactory, FakeUowFactory(uow)),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 21, 20, 0),
    )

    result = asyncio.run(service.execute())

    assert result.deleted_1m_rows == 16
    assert result.deleted_1d_rows == 3
    assert bars.deleted_1m_calls == [
        (date(2026, 4, 9), None),
        (date(2026, 4, 21), ["after_hours", "pre_market"]),
    ]
    assert bars.deleted_1d_threshold == date(2016, 4, 21)
    assert uow.committed is True
    assert len(state_repository.upserted) == 1
    assert state_repository.upserted[0].earliest_1m_trading_day == date(2026, 4, 9)
