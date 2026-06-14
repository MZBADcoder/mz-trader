"""Integration tests for market bars ingestion and query paths."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from fastapi.testclient import TestClient

from application.services.market_data.run_current_day_bars_refresh import (
    RunCurrentDayBarsRefreshService,
)
from application.services.market_data.run_historical_bars_gap_reconciliation import (
    RunHistoricalBarsGapReconciliationService,
)
from application.services.market_data.run_post_close_bars_finalizer import (
    RunPostCloseBarsFinalizerService,
)
from application.services.market_data.run_ticker_bars_bootstrap import (
    RunTickerBarsBootstrapService,
)
from domain.entities import (
    CanonicalBar,
    MarketDataMode,
    ProviderBar,
    SnapshotCoordinatorRefreshResult,
    TickerBarsState,
)
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient
from infrastructure.repositories.market_bar_repository import MarketBarRepository
from infrastructure.repositories.market_ticker_bars_state_repository import (
    MarketTickerBarsStateRepository,
)
from infrastructure.repositories.watchlist_repository import WatchlistRepository


def _dt(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _register_and_authenticate(client: TestClient, *, email: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["user"]["id"], payload["access_token"]


def _provider_bar(
    *,
    at: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    vw: float | None = None,
    trade_count: int = 1,
) -> ProviderBar:
    return ProviderBar(
        time=at,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        vw=vw if vw is not None else close,
        trade_count=trade_count,
        provider_updated_at=at,
    )


def _canonical_1m(
    *,
    ticker: str = "AAPL",
    at: datetime,
    trading_day: date,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    vw: float | None = None,
    trade_count: int = 1,
    is_final: bool = True,
) -> CanonicalBar:
    return CanonicalBar(
        ticker=ticker,
        adjustment="split_adjusted",
        granularity="1m",
        bucket_start_at=at,
        trading_day=trading_day,
        session_kind="regular",
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        vw=vw if vw is not None else close,
        trade_count=trade_count,
        provider_updated_at=at,
        is_final=is_final,
        first_synced_at=at,
        last_synced_at=at,
    )


def _canonical_1d(
    *,
    ticker: str = "AAPL",
    trading_day: date,
    bucket_start_at: datetime,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: int = 1000,
    vw: float | None = 100.4,
    trade_count: int = 10,
) -> CanonicalBar:
    return CanonicalBar(
        ticker=ticker,
        adjustment="split_adjusted",
        granularity="1d",
        bucket_start_at=bucket_start_at,
        trading_day=trading_day,
        session_kind="regular",
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        vw=vw,
        trade_count=trade_count,
        provider_updated_at=bucket_start_at,
        is_final=True,
        first_synced_at=bucket_start_at,
        last_synced_at=bucket_start_at,
    )


def _ready_state(*, ticker: str, now: datetime) -> TickerBarsState:
    return TickerBarsState(
        ticker=ticker,
        status="ready",
        bootstrap_requested_at=now,
        bootstrap_started_at=now,
        bootstrap_finished_at=now,
        bootstrap_failed_at=None,
        last_reconciled_at=now,
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


class ScriptedProviderBarsClient(MassiveBarsClient):
    """Deterministic bars client at the post-Massive-adapter ProviderBar boundary."""

    def __init__(self, responses: list[list[ProviderBar]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def close(self) -> None:
        return None

    async def fetch_range(self, **kwargs: Any) -> list[ProviderBar]:
        self.calls.append(kwargs)
        if not self.responses:
            return []
        return self.responses.pop(0)


class NoopBootstrapService:
    """Bootstrap replacement used when reconciliation should only process ready tickers."""

    def __init__(self) -> None:
        self.tickers: list[str] | None = None

    async def execute(self, *, tickers: list[str] | None = None) -> SnapshotCoordinatorRefreshResult:
        self.tickers = tickers
        return SnapshotCoordinatorRefreshResult(
            status="completed",
            total_tickers=len(tickers or []),
            refreshed_tickers=0,
            failed_tickers=[],
        )


def _seed_watchlist(session_factory, *, user_id: str, tickers: list[str]) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            repository = WatchlistRepository(session)
            for ticker in tickers:
                await repository.add(user_id=user_id, ticker=ticker)
            await session.commit()

    asyncio.run(seed())


def _seed_ticker_state(session_factory, state: TickerBarsState) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            repository = MarketTickerBarsStateRepository(session)
            await repository.upsert(state)
            await session.commit()

    asyncio.run(seed())


def _seed_1m_bars(session_factory, bars: list[CanonicalBar]) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            repository = MarketBarRepository(session)
            for start in range(0, len(bars), 1000):
                await repository.upsert_1m(bars[start : start + 1000])
            await session.commit()

    asyncio.run(seed())


def _seed_1d_bars(session_factory, bars: list[CanonicalBar]) -> None:
    async def seed() -> None:
        async with session_factory() as session:
            repository = MarketBarRepository(session)
            await repository.upsert_1d(bars)
            await session.commit()

    asyncio.run(seed())


def _regular_minute_rows_for_reconciliation(
    *,
    calendar: UsStockCalendar,
    anchor_day: date,
    effective_now: datetime,
    omit: set[datetime],
) -> list[CanonicalBar]:
    rows: list[CanonicalBar] = []
    for trading_day in calendar.previous_trading_days(anchor_day, 10):
        window = calendar.regular_session_window(trading_day)
        current = window.start_at
        upper_bound = min(window.end_at, effective_now)
        while current + timedelta(minutes=1) <= upper_bound:
            if current not in omit:
                rows.append(
                    _canonical_1m(
                        at=current,
                        trading_day=trading_day,
                        open_price=100.0,
                        high=101.0,
                        low=99.0,
                        close=100.5,
                        volume=100,
                    )
                )
            current += timedelta(minutes=1)
    return rows


def _daily_rows_for_reconciliation(
    *,
    calendar: UsStockCalendar,
    anchor_day: date,
    effective_now: datetime,
    omit: set[date],
) -> list[CanonicalBar]:
    completed_end_day = anchor_day
    market_day = calendar.to_market_date(effective_now)
    if calendar.is_trading_day(market_day) and anchor_day == market_day:
        completed_end_day = calendar.previous_trading_day(anchor_day)
    start_day = calendar.previous_trading_days(anchor_day, 90)[0]
    return [
        _canonical_1d(
            trading_day=trading_day,
            bucket_start_at=calendar.regular_session_window(trading_day).start_at,
        )
        for trading_day in calendar.trading_days_between(start_day, completed_end_day)
        if trading_day not in omit
    ]


def _list_1m_bars(session_factory, *, ticker: str, start_at: datetime, end_at: datetime) -> list[CanonicalBar]:
    async def load() -> list[CanonicalBar]:
        async with session_factory() as session:
            repository = MarketBarRepository(session)
            return await repository.list_1m(
                ticker=ticker,
                adjustment="split_adjusted",
                start_at=start_at,
                end_at=end_at,
            )

    return asyncio.run(load())


def _list_1d_bars(session_factory, *, ticker: str, start_day: date, end_day: date) -> list[CanonicalBar]:
    async def load() -> list[CanonicalBar]:
        async with session_factory() as session:
            repository = MarketBarRepository(session)
            return await repository.list_1d(
                ticker=ticker,
                adjustment="split_adjusted",
                start_day=start_day,
                end_day=end_day,
            )

    return asyncio.run(load())


def _get_ticker_state(session_factory, *, ticker: str) -> TickerBarsState | None:
    async def load() -> TickerBarsState | None:
        async with session_factory() as session:
            repository = MarketTickerBarsStateRepository(session)
            return await repository.get(ticker=ticker)

    return asyncio.run(load())


def test_current_day_refresh_persists_provider_minutes_and_bars_api_reads_them(
    client: TestClient,
    session_factory,
) -> None:
    user_id, access_token = _register_and_authenticate(client, email="bars-refresh@example.com")
    _seed_watchlist(session_factory, user_id=user_id, tickers=["AAPL"])
    bars_client = ScriptedProviderBarsClient(
        responses=[
            [
                _provider_bar(
                    at=_dt(2026, 4, 15, 13, 30),
                    open_price=100.0,
                    high=101.5,
                    low=99.5,
                    close=101.0,
                    volume=100,
                    vw=100.8,
                    trade_count=4,
                ),
                _provider_bar(
                    at=_dt(2026, 4, 15, 13, 34),
                    open_price=101.0,
                    high=102.0,
                    low=100.8,
                    close=101.8,
                    volume=150,
                    vw=101.6,
                    trade_count=5,
                ),
            ]
        ]
    )
    service = RunCurrentDayBarsRefreshService(
        uow_factory=SqlAlchemyUnitOfWorkFactory(session_factory),
        bars_client=bars_client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: datetime(2026, 4, 15, 13, 34, 30, tzinfo=UTC),
    )

    result = asyncio.run(service.execute())

    assert result.status == "completed"
    assert result.total_tickers == 1
    assert result.refreshed_tickers == 1
    assert result.failed_tickers == []
    assert bars_client.calls[0]["ticker"] == "AAPL"
    assert bars_client.calls[0]["timespan"] == "minute"
    persisted = _list_1m_bars(
        session_factory,
        ticker="AAPL",
        start_at=_dt(2026, 4, 15, 13, 25),
        end_at=_dt(2026, 4, 15, 13, 35),
    )
    assert [(bar.bucket_start_at, bar.session_kind, bar.is_final) for bar in persisted] == [
        (_dt(2026, 4, 15, 13, 30), "regular", True),
        (_dt(2026, 4, 15, 13, 34), "regular", False),
    ]
    state = _get_ticker_state(session_factory, ticker="AAPL")
    assert state is not None
    assert state.status == "ready"
    assert state.last_1m_bucket_start_at == _dt(2026, 4, 15, 13, 34)

    response = client.get(
        "/api/v1/market-data/bars",
        params={
            "ticker": "AAPL",
            "resolution": "1m",
            "session": "regular",
            "from": "2026-04-15T13:30:00Z",
            "to": "2026-04-15T13:35:00Z",
            "fill": "none",
        },
        headers={"Authorization": f"Bearer {access_token}", "X-Request-ID": "reqbars01"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [bar["time"] for bar in payload["bars"]] == [
        "2026-04-15T13:30:00Z",
        "2026-04-15T13:34:00Z",
    ]
    assert payload["bars"][0]["close"] == 101.0
    assert payload["bars"][1]["is_final"] is False
    assert payload["meta"]["source_granularity"] == "1m"
    assert payload["meta"]["data_source"] == "db"
    assert payload["meta"]["readiness"] == "ready"
    assert payload["meta"]["contains_partial_bar"] is True
    assert payload["meta"]["request_id"] == "reqbars01"
    assert response.headers["X-Data-Source"] == "db"
    assert response.headers["X-Partial-Range"] == "false"


def test_bars_api_aggregates_intraday_resolution_and_carry_forward_fill(
    client: TestClient,
    session_factory,
) -> None:
    _, access_token = _register_and_authenticate(client, email="bars-aggregate@example.com")
    _seed_1m_bars(
        session_factory,
        [
            _canonical_1m(
                at=_dt(2026, 4, 15, 13, 30),
                trading_day=date(2026, 4, 15),
                open_price=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=100,
                vw=100.2,
                trade_count=4,
            ),
            _canonical_1m(
                at=_dt(2026, 4, 15, 13, 31),
                trading_day=date(2026, 4, 15),
                open_price=100.5,
                high=103.0,
                low=100.0,
                close=102.0,
                volume=300,
                vw=101.8,
                trade_count=6,
            ),
            _canonical_1m(
                at=_dt(2026, 4, 15, 13, 34),
                trading_day=date(2026, 4, 15),
                open_price=102.0,
                high=102.5,
                low=98.5,
                close=99.5,
                volume=200,
                vw=100.0,
                trade_count=5,
            ),
        ],
    )

    aggregate_response = client.get(
        "/api/v1/market-data/bars",
        params={
            "ticker": "AAPL",
            "resolution": "5m",
            "session": "regular",
            "from": "2026-04-15T13:30:00Z",
            "to": "2026-04-15T13:35:00Z",
            "fill": "none",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    fill_response = client.get(
        "/api/v1/market-data/bars",
        params={
            "ticker": "AAPL",
            "resolution": "1m",
            "session": "regular",
            "from": "2026-04-15T13:30:00Z",
            "to": "2026-04-15T13:33:00Z",
            "fill": "carry_forward",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert aggregate_response.status_code == 200
    aggregate_payload = aggregate_response.json()
    assert len(aggregate_payload["bars"]) == 1
    aggregate_bar = aggregate_payload["bars"][0]
    assert aggregate_bar == {
        "time": "2026-04-15T13:30:00Z",
        "open": 100.0,
        "high": 103.0,
        "low": 98.5,
        "close": 99.5,
        "volume": 600,
        "vw": 100.93333333333334,
        "trade_count": 15,
        "is_final": True,
        "is_synthetic": False,
    }
    assert aggregate_payload["meta"]["resolution"] == "5m"
    assert aggregate_payload["meta"]["source_granularity"] == "1m"

    assert fill_response.status_code == 200
    fill_payload = fill_response.json()
    assert [(bar["time"], bar["close"], bar["is_synthetic"]) for bar in fill_payload["bars"]] == [
        ("2026-04-15T13:30:00Z", 100.5, False),
        ("2026-04-15T13:31:00Z", 102.0, False),
        ("2026-04-15T13:32:00Z", 102.0, True),
    ]
    assert fill_payload["bars"][2]["volume"] == 0
    assert fill_payload["bars"][2]["vw"] is None
    assert fill_payload["meta"]["fill"] == "carry_forward"


def test_post_close_finalizer_persists_daily_bar_and_day_query_reads_1d_storage(
    client: TestClient,
    session_factory,
) -> None:
    user_id, access_token = _register_and_authenticate(client, email="bars-finalizer@example.com")
    _seed_watchlist(session_factory, user_id=user_id, tickers=["AAPL"])
    _seed_ticker_state(session_factory, _ready_state(ticker="AAPL", now=_dt(2026, 4, 15, 20, 1)))
    bars_client = ScriptedProviderBarsClient(
        responses=[
            [
                _provider_bar(
                    at=_dt(2026, 4, 15, 13, 30),
                    open_price=100.0,
                    high=101.0,
                    low=99.5,
                    close=100.5,
                    volume=100,
                    vw=100.4,
                    trade_count=4,
                ),
                _provider_bar(
                    at=_dt(2026, 4, 15, 19, 59),
                    open_price=101.0,
                    high=104.0,
                    low=100.8,
                    close=103.5,
                    volume=300,
                    vw=103.0,
                    trade_count=10,
                ),
            ]
        ]
    )
    service = RunPostCloseBarsFinalizerService(
        uow_factory=SqlAlchemyUnitOfWorkFactory(session_factory),
        bars_client=bars_client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 15, 20, 30),
    )

    result = asyncio.run(service.execute())

    assert result.status == "completed"
    assert result.total_tickers == 1
    assert result.refreshed_tickers == 1
    daily_rows = _list_1d_bars(
        session_factory,
        ticker="AAPL",
        start_day=date(2026, 4, 15),
        end_day=date(2026, 4, 15),
    )
    assert len(daily_rows) == 1
    daily_row = daily_rows[0]
    assert daily_row.bucket_start_at == _dt(2026, 4, 15, 13, 30)
    assert daily_row.open == 100.0
    assert daily_row.high == 104.0
    assert daily_row.low == 99.5
    assert daily_row.close == 103.5
    assert daily_row.volume == 400
    assert daily_row.vw == 102.35
    assert daily_row.is_final is True

    response = client.get(
        "/api/v1/market-data/bars",
        params={
            "ticker": "AAPL",
            "resolution": "1D",
            "session": "regular",
            "from": "2026-04-15T13:30:00Z",
            "to": "2026-04-16T04:00:00Z",
            "fill": "none",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["bars"]) == 1
    assert payload["bars"][0]["time"] == "2026-04-15T13:30:00Z"
    assert payload["bars"][0]["close"] == 103.5
    assert payload["bars"][0]["is_final"] is True
    assert payload["meta"]["source_granularity"] == "1d"
    assert payload["meta"]["readiness"] == "ready"


def test_bootstrap_writes_minute_and_completed_daily_canonical_storage(session_factory) -> None:
    bars_client = ScriptedProviderBarsClient(
        responses=[
            [
                _provider_bar(
                    at=_dt(2026, 4, 14, 4, 0),
                    open_price=95.0,
                    high=99.0,
                    low=94.0,
                    close=98.0,
                    volume=1_000,
                    vw=97.5,
                    trade_count=20,
                )
            ],
            [
                _provider_bar(
                    at=_dt(2026, 4, 15, 8, 0),
                    open_price=98.0,
                    high=98.5,
                    low=97.8,
                    close=98.2,
                    volume=50,
                    vw=98.1,
                    trade_count=2,
                ),
                _provider_bar(
                    at=_dt(2026, 4, 15, 13, 30),
                    open_price=99.0,
                    high=100.0,
                    low=98.8,
                    close=99.5,
                    volume=100,
                    vw=99.4,
                    trade_count=4,
                ),
            ],
        ]
    )
    service = RunTickerBarsBootstrapService(
        uow_factory=SqlAlchemyUnitOfWorkFactory(session_factory),
        bars_client=bars_client,
        calendar=UsStockCalendar(),
        mode=MarketDataMode(delay_minutes=0),
        now_provider=lambda: _dt(2026, 4, 15, 15, 0),
    )

    result = asyncio.run(service.execute(tickers=["AAPL"]))

    assert result.status == "completed"
    assert result.total_tickers == 1
    assert result.refreshed_tickers == 1
    assert [call["timespan"] for call in bars_client.calls] == ["day", "minute"]
    assert bars_client.calls[1]["from_value"] == str(int(_dt(2026, 4, 2, 13, 30).timestamp() * 1000))
    assert bars_client.calls[1]["to_value"] == str(int(_dt(2026, 4, 15, 15, 0).timestamp() * 1000))
    minute_rows = _list_1m_bars(
        session_factory,
        ticker="AAPL",
        start_at=_dt(2026, 4, 15, 8, 0),
        end_at=_dt(2026, 4, 15, 13, 31),
    )
    assert [(row.bucket_start_at, row.session_kind, row.is_final) for row in minute_rows] == [
        (_dt(2026, 4, 15, 13, 30), "regular", True),
    ]
    daily_rows = _list_1d_bars(
        session_factory,
        ticker="AAPL",
        start_day=date(2026, 4, 14),
        end_day=date(2026, 4, 14),
    )
    assert len(daily_rows) == 1
    assert daily_rows[0].bucket_start_at == _dt(2026, 4, 14, 13, 30)
    assert daily_rows[0].close == 98.0
    state = _get_ticker_state(session_factory, ticker="AAPL")
    assert state is not None
    assert state.status == "ready"
    assert state.earliest_1m_trading_day == date(2026, 4, 15)
    assert state.last_1m_trading_day == date(2026, 4, 15)
    assert state.earliest_1d_trading_day == date(2026, 4, 14)
    assert state.latest_1d_trading_day == date(2026, 4, 14)


def test_historical_reconciliation_backfills_missing_minute_and_daily_gaps(
    client: TestClient,
    session_factory,
) -> None:
    user_id, _ = _register_and_authenticate(client, email="bars-reconcile@example.com")
    _seed_watchlist(session_factory, user_id=user_id, tickers=["AAPL"])
    calendar = UsStockCalendar()
    anchor_day = date(2026, 4, 21)
    regular_window = calendar.regular_session_window(anchor_day)
    effective_now = regular_window.start_at + timedelta(minutes=3)
    missing_minute = regular_window.start_at + timedelta(minutes=1)
    missing_day = calendar.previous_trading_day(anchor_day)
    _seed_ticker_state(session_factory, _ready_state(ticker="AAPL", now=effective_now))
    _seed_1m_bars(
        session_factory,
        _regular_minute_rows_for_reconciliation(
            calendar=calendar,
            anchor_day=anchor_day,
            effective_now=effective_now,
            omit={missing_minute},
        ),
    )
    _seed_1d_bars(
        session_factory,
        _daily_rows_for_reconciliation(
            calendar=calendar,
            anchor_day=anchor_day,
            effective_now=effective_now,
            omit={missing_day},
        ),
    )
    bars_client = ScriptedProviderBarsClient(
        responses=[
            [
                _provider_bar(
                    at=missing_minute,
                    open_price=110.0,
                    high=111.0,
                    low=109.5,
                    close=110.5,
                    volume=250,
                    vw=110.4,
                    trade_count=7,
                )
            ],
            [
                _provider_bar(
                    at=datetime(missing_day.year, missing_day.month, missing_day.day, 4, 0, tzinfo=UTC),
                    open_price=105.0,
                    high=108.0,
                    low=104.0,
                    close=107.5,
                    volume=10_000,
                    vw=106.8,
                    trade_count=120,
                )
            ],
        ]
    )
    bootstrap_service = NoopBootstrapService()
    service = RunHistoricalBarsGapReconciliationService(
        uow_factory=SqlAlchemyUnitOfWorkFactory(session_factory),
        bars_client=bars_client,
        calendar=calendar,
        bootstrap_service=cast(RunTickerBarsBootstrapService, bootstrap_service),
        mode=MarketDataMode(delay_minutes=0),
        max_provider_calls_per_ticker=4,
        now_provider=lambda: effective_now,
    )

    result = asyncio.run(service.execute())

    assert result.status == "completed"
    assert result.total_tickers == 1
    assert result.processed_tickers == 1
    assert result.failed_tickers == []
    assert bootstrap_service.tickers == []
    assert [(call["timespan"], call["ticker"]) for call in bars_client.calls] == [
        ("minute", "AAPL"),
        ("day", "AAPL"),
    ]
    assert bars_client.calls[0]["from_value"] == str(int(missing_minute.timestamp() * 1000))
    assert bars_client.calls[0]["to_value"] == str(int((missing_minute + timedelta(minutes=1)).timestamp() * 1000))
    assert bars_client.calls[1]["from_value"] == missing_day.isoformat()
    assert bars_client.calls[1]["to_value"] == missing_day.isoformat()

    minute_rows = _list_1m_bars(
        session_factory,
        ticker="AAPL",
        start_at=missing_minute,
        end_at=missing_minute + timedelta(minutes=1),
    )
    assert len(minute_rows) == 1
    assert minute_rows[0].bucket_start_at == missing_minute
    assert minute_rows[0].session_kind == "regular"
    assert minute_rows[0].close == 110.5
    assert minute_rows[0].is_final is True
    daily_rows = _list_1d_bars(
        session_factory,
        ticker="AAPL",
        start_day=missing_day,
        end_day=missing_day,
    )
    assert len(daily_rows) == 1
    assert daily_rows[0].bucket_start_at == calendar.regular_session_window(missing_day).start_at
    assert daily_rows[0].close == 107.5
    assert daily_rows[0].is_final is True
    state = _get_ticker_state(session_factory, ticker="AAPL")
    assert state is not None
    assert state.status == "ready"
    assert state.last_1m_bucket_start_at == missing_minute
    assert state.latest_1d_trading_day == missing_day
