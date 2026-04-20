"""Tests for bars maintenance state helpers and retention cleanup."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import cast

from application.services.market_data._bars_maintenance_support import (
    build_ready_state,
    clamp_state_to_retention,
)
from application.services.market_data.run_bars_retention_cleanup import RunBarsRetentionCleanupService
from domain.entities import CanonicalBar, MarketDataMode, TickerBarsState
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory


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


def _canonical_1m(*, trading_day: date, bucket_start_at: datetime) -> CanonicalBar:
    return CanonicalBar(
        ticker="AAPL",
        adjustment="split_adjusted",
        granularity="1m",
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


class FakeBarsRepository:
    def __init__(self) -> None:
        self.deleted_1m_threshold: date | None = None
        self.deleted_1d_threshold: date | None = None

    async def delete_1m_before(self, *, threshold_day: date) -> int:
        self.deleted_1m_threshold = threshold_day
        return 12

    async def delete_1d_before(self, *, threshold_day: date) -> int:
        self.deleted_1d_threshold = threshold_day
        return 3


class FakeTickerBarsStateRepository:
    def __init__(self, states: list[TickerBarsState]) -> None:
        self._states = states
        self.upserted: list[TickerBarsState] = []

    async def list_by_statuses(self, *, statuses: list[str]) -> list[TickerBarsState]:
        return [state for state in self._states if state.status in statuses]

    async def upsert(self, state: TickerBarsState) -> None:
        self.upserted.append(state)


class FakeUow:
    def __init__(self, bars: FakeBarsRepository, state_repository: FakeTickerBarsStateRepository) -> None:
        self.bars = bars
        self.ticker_bars_state = state_repository
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

    assert result.deleted_1m_rows == 12
    assert result.deleted_1d_rows == 3
    assert bars.deleted_1m_threshold == date(2026, 4, 9)
    assert bars.deleted_1d_threshold == date(2016, 4, 21)
    assert uow.committed is True
    assert len(state_repository.upserted) == 1
    assert state_repository.upserted[0].earliest_1m_trading_day == date(2026, 4, 9)
