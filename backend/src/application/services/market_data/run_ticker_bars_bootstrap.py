"""Run bootstrap for pending ticker bars state."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Callable

from application.services.market_data._bars_maintenance_support import (
    build_canonical_1m_rows,
    build_initializing_state,
    build_ready_state,
    retain_latest_extended_session_rows,
)
from domain.entities import CanonicalBar, MarketDataMode, SnapshotCoordinatorRefreshResult, TickerBarsState
from domain.rules import (
    MARKET_BARS_1D_RETENTION_YEARS,
    MARKET_BARS_1M_RETENTION_TRADING_DAYS,
    MARKET_BARS_INITIALIZING_TIMEOUT_MINUTES,
)
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient


logger = logging.getLogger(__name__)


class RunTickerBarsBootstrapService:
    """Initialize bars history for pending or degraded tickers."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        bars_client: MassiveBarsClient,
        calendar: UsStockCalendar,
        mode: MarketDataMode,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._bars_client = bars_client
        self._calendar = calendar
        self._mode = mode
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self, *, tickers: list[str] | None = None) -> SnapshotCoordinatorRefreshResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        async with self._uow_factory.build() as uow:
            if tickers is None:
                pending_states = await uow.ticker_bars_state.list_by_statuses(
                    statuses=["pending", "failed", "degraded", "initializing"]
                )
                target_tickers = []
                for state in pending_states:
                    if state.status == "initializing":
                        if not self._initializing_timed_out(state=state, effective_now=effective_now):
                            continue
                        await uow.ticker_bars_state.mark_failed(
                            ticker=state.ticker,
                            failed_at=effective_now,
                            error_message="bootstrap initialization timed out before periodic retry.",
                        )
                    target_tickers.append(state.ticker)
                await uow.commit()
            else:
                target_tickers = sorted(set(tickers))

        bootstrapped = 0
        failed_tickers: list[str] = []
        for ticker in target_tickers:
            try:
                did_bootstrap = await self._bootstrap_ticker(ticker=ticker, effective_now=effective_now)
            except Exception as exc:
                logger.warning("ticker bars bootstrap failed", extra={"ticker": ticker})
                async with self._uow_factory.build() as uow:
                    await uow.ticker_bars_state.mark_failed(
                        ticker=ticker,
                        failed_at=self._now_provider().astimezone(UTC),
                        error_message=_bootstrap_failure_message(exc),
                    )
                    await uow.commit()
                failed_tickers.append(ticker)
                continue
            if did_bootstrap:
                bootstrapped += 1

        return SnapshotCoordinatorRefreshResult(
            status="completed",
            total_tickers=len(target_tickers),
            refreshed_tickers=bootstrapped,
            failed_tickers=failed_tickers,
        )

    def _initializing_timed_out(self, *, state: TickerBarsState, effective_now: datetime) -> bool:
        if state.bootstrap_started_at is None:
            return True
        return state.bootstrap_started_at <= effective_now - timedelta(minutes=MARKET_BARS_INITIALIZING_TIMEOUT_MINUTES)

    async def _bootstrap_ticker(self, *, ticker: str, effective_now: datetime) -> bool:
        now_synced_at = self._now_provider().astimezone(UTC)
        anchor_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(effective_now))
        minute_days = self._calendar.previous_trading_days(anchor_day, MARKET_BARS_1M_RETENTION_TRADING_DAYS)
        minute_start_day = minute_days[0]
        daily_start_day = self._subtract_years(anchor_day, MARKET_BARS_1D_RETENTION_YEARS)

        async with self._uow_factory.build() as uow:
            existing_state = await uow.ticker_bars_state.get_for_update(ticker=ticker)
            if existing_state is not None and existing_state.status == "ready":
                return False
            if (
                existing_state is not None
                and existing_state.status == "initializing"
                and not self._initializing_timed_out(state=existing_state, effective_now=effective_now)
            ):
                return False
            await uow.ticker_bars_state.upsert(
                build_initializing_state(ticker=ticker, now=now_synced_at, existing=existing_state)
            )
            await uow.commit()

        completed_daily_end_day = anchor_day
        current_trading_day = self._current_trading_day(effective_now=effective_now)
        if current_trading_day is not None and anchor_day == current_trading_day:
            completed_daily_end_day = self._calendar.previous_trading_day(anchor_day)
        daily_provider_bars = await self._bars_client.fetch_range(
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_value=daily_start_day.isoformat(),
            to_value=completed_daily_end_day.isoformat(),
            adjusted=True,
        )
        daily_rows = self._to_daily_rows(
            ticker=ticker,
            provider_bars=daily_provider_bars,
            synced_at=now_synced_at,
        )

        minute_start_at = self._calendar.session_window(minute_start_day, "pre_market").start_at
        current_window_end = self._minute_window_end(anchor_day=anchor_day, effective_now=effective_now)
        minute_provider_bars = await self._bars_client.fetch_range(
            ticker=ticker,
            multiplier=1,
            timespan="minute",
            from_value=str(int(minute_start_at.timestamp() * 1000)),
            to_value=str(int(current_window_end.timestamp() * 1000)),
            adjusted=True,
        )
        minute_rows = build_canonical_1m_rows(
            ticker=ticker,
            adjustment="split_adjusted",
            provider_bars=minute_provider_bars,
            calendar=self._calendar,
            effective_now=effective_now,
            synced_at=now_synced_at,
        )
        minute_rows = retain_latest_extended_session_rows(
            rows=minute_rows,
            latest_extended_trading_day=anchor_day,
        )

        async with self._uow_factory.build() as uow:
            if daily_rows:
                await uow.bars.upsert_1d(daily_rows)
            if minute_rows:
                await uow.bars.upsert_1m(minute_rows)
            current_state = await uow.ticker_bars_state.get_for_update(ticker=ticker)
            await uow.ticker_bars_state.upsert(
                build_ready_state(
                    ticker=ticker,
                    now=now_synced_at,
                    minute_rows=minute_rows,
                    daily_rows=daily_rows,
                    existing=current_state,
                )
            )
            await uow.commit()
        return True

    def _to_daily_rows(self, *, ticker: str, provider_bars, synced_at: datetime) -> list[CanonicalBar]:
        rows: list[CanonicalBar] = []
        for bar in provider_bars:
            trading_day = self._calendar.to_market_date(bar.time)
            rows.append(
                CanonicalBar(
                    ticker=ticker,
                    adjustment="split_adjusted",
                    granularity="1d",
                    bucket_start_at=self._calendar.regular_session_window(trading_day).start_at,
                    trading_day=trading_day,
                    session_kind="regular",
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    vw=bar.vw,
                    trade_count=bar.trade_count,
                    provider_updated_at=bar.provider_updated_at,
                    is_final=True,
                    first_synced_at=synced_at,
                    last_synced_at=synced_at,
                )
            )
        return rows

    def _minute_window_end(self, *, anchor_day: date, effective_now: datetime) -> datetime:
        local_day = self._calendar.to_market_date(effective_now)
        if local_day != anchor_day or not self._calendar.is_trading_day(anchor_day):
            return self._calendar.session_window(anchor_day, "after_hours").end_at
        return min(self._calendar.session_window(anchor_day, "after_hours").end_at, effective_now)

    def _subtract_years(self, value: date, years: int) -> date:
        try:
            return value.replace(year=value.year - years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year - years)

    def _current_trading_day(self, *, effective_now: datetime) -> date | None:
        market_day = self._calendar.to_market_date(effective_now)
        if not self._calendar.is_trading_day(market_day):
            return None
        return market_day


def _bootstrap_failure_message(exc: Exception) -> str:
    detail_source: object | None = getattr(exc, "orig", None)
    if detail_source is None:
        detail_source = exc.__cause__
    detail = str(detail_source or exc).strip()
    if not detail:
        return "ticker bars bootstrap failed"
    return f"{type(exc).__name__}: {detail}"
