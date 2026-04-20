"""Bars service tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from application.services.market_data.get_bars import GetBarsService
from domain.entities import CanonicalBar, MarketDataMode, TickerBarsState
from domain.rules import validate_bars_query
from infrastructure.calendar import UsStockCalendar


def _dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


class FakeBarsRepository:
    def __init__(self) -> None:
        self.rows_1m: list[CanonicalBar] = []
        self.rows_1d: list[CanonicalBar] = []

    async def list_1m(self, *, ticker, adjustment, start_at, end_at, session_kind=None):
        rows = [
            row
            for row in self.rows_1m
            if row.ticker == ticker
            and row.adjustment == adjustment
            and row.bucket_start_at >= start_at
            and row.bucket_start_at < end_at
            and (session_kind is None or row.session_kind == session_kind)
        ]
        return sorted(rows, key=lambda item: item.bucket_start_at)

    async def list_1d(self, *, ticker, adjustment, start_day, end_day):
        rows = [
            row
            for row in self.rows_1d
            if row.ticker == ticker
            and row.adjustment == adjustment
            and start_day <= row.trading_day <= end_day
        ]
        return sorted(rows, key=lambda item: item.trading_day)


class FakeTickerBarsStateRepository:
    def __init__(self) -> None:
        self.state_by_ticker: dict[str, TickerBarsState] = {}

    async def get(self, *, ticker: str) -> TickerBarsState | None:
        return self.state_by_ticker.get(ticker)


class FakeUow:
    def __init__(self, repository: FakeBarsRepository, state_repository: FakeTickerBarsStateRepository) -> None:
        self.bars = repository
        self.ticker_bars_state = state_repository

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeUowFactory:
    def __init__(self, repository: FakeBarsRepository, state_repository: FakeTickerBarsStateRepository) -> None:
        self.repository = repository
        self.state_repository = state_repository

    def build(self) -> FakeUow:
        return FakeUow(self.repository, self.state_repository)


def _canonical_1m(
    *,
    ticker: str,
    bucket_start_at: datetime,
    trading_day: date,
    close: float,
    session_kind: str = "regular",
) -> CanonicalBar:
    return CanonicalBar(
        ticker=ticker,
        adjustment="split_adjusted",
        granularity="1m",
        bucket_start_at=bucket_start_at,
        trading_day=trading_day,
        session_kind=session_kind,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100,
        vw=close,
        trade_count=1,
        provider_updated_at=bucket_start_at,
        is_final=True,
        first_synced_at=bucket_start_at,
        last_synced_at=bucket_start_at,
    )


def _canonical_1d(*, ticker: str, trading_day: date, close: float, bucket_start_at: datetime) -> CanonicalBar:
    return CanonicalBar(
        ticker=ticker,
        adjustment="split_adjusted",
        granularity="1d",
        bucket_start_at=bucket_start_at,
        trading_day=trading_day,
        session_kind="regular",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        vw=close,
        trade_count=10,
        provider_updated_at=bucket_start_at,
        is_final=True,
        first_synced_at=bucket_start_at,
        last_synced_at=bucket_start_at,
    )


def test_get_bars_service_returns_empty_regular_intraday_before_open() -> None:
    repository = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository()
    service = GetBarsService(
        uow_factory=FakeUowFactory(repository, state_repository),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 15, 13, 0),  # 09:00 ET
    )
    query = validate_bars_query(
        ticker="AAPL",
        resolution="1m",
        session="regular",
        adjustment="split_adjusted",
        fill="carry_forward",
        include_partial=True,
        from_time=None,
        to_time=None,
        count_back=10,
    )

    result = asyncio.run(service.execute(user_id="user-1", query=query))

    assert result.bars == []
    assert result.meta.calendar_shifted is False
    assert result.meta.data_source == "db"
    assert result.meta.readiness == "pending"
    assert result.meta.partial_range is True


def test_get_bars_service_marks_pending_state_as_partial_range() -> None:
    repository = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository()
    now = _dt(2026, 4, 15, 14, 0)
    state_repository.state_by_ticker["AAPL"] = TickerBarsState(
        ticker="AAPL",
        status="pending",
        bootstrap_requested_at=now,
        bootstrap_started_at=None,
        bootstrap_finished_at=None,
        bootstrap_failed_at=None,
        last_reconciled_at=None,
        earliest_1m_trading_day=None,
        last_1m_trading_day=None,
        last_1m_bucket_start_at=None,
        earliest_1d_trading_day=None,
        latest_1d_trading_day=None,
        last_error_code=None,
        last_error_message=None,
        created_at=now,
        updated_at=now,
    )
    service = GetBarsService(
        uow_factory=FakeUowFactory(repository, state_repository),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: now,
    )
    query = validate_bars_query(
        ticker="AAPL",
        resolution="1m",
        session="regular",
        adjustment="split_adjusted",
        fill="none",
        include_partial=True,
        from_time=_dt(2026, 4, 15, 13, 30),
        to_time=_dt(2026, 4, 15, 13, 35),
        count_back=None,
    )

    result = asyncio.run(service.execute(user_id="user-1", query=query))

    assert result.bars == []
    assert result.meta.readiness == "pending"
    assert result.meta.partial_range is True
    assert result.meta.data_source == "db"


def test_get_bars_service_builds_daily_series_from_1d_history_and_current_day_1m() -> None:
    repository = FakeBarsRepository()
    state_repository = FakeTickerBarsStateRepository()
    repository.rows_1d.append(
        _canonical_1d(
            ticker="AAPL",
            trading_day=date(2026, 4, 14),
            close=99.0,
            bucket_start_at=_dt(2026, 4, 14, 13, 30),
        )
    )
    repository.rows_1m.extend(
        [
            _canonical_1m(
                ticker="AAPL",
                trading_day=date(2026, 4, 15),
                bucket_start_at=_dt(2026, 4, 15, 13, 30),
                close=100.0,
            ),
            _canonical_1m(
                ticker="AAPL",
                trading_day=date(2026, 4, 15),
                bucket_start_at=_dt(2026, 4, 15, 13, 31),
                close=101.0,
            ),
        ]
    )
    service = GetBarsService(
        uow_factory=FakeUowFactory(repository, state_repository),
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 15, 13, 32),
    )
    query = validate_bars_query(
        ticker="AAPL",
        resolution="1D",
        session="regular",
        adjustment="split_adjusted",
        fill="carry_forward",
        include_partial=True,
        from_time=None,
        to_time=None,
        count_back=5,
    )

    result = asyncio.run(service.execute(user_id="user-1", query=query))

    assert len(result.bars) == 2
    assert result.bars[0].close == 99.0
    assert result.bars[0].is_final is True
    assert result.bars[1].close == 101.0
    assert result.bars[1].is_final is False
    assert result.meta.data_source == "db"
    assert result.meta.readiness == "ready"
