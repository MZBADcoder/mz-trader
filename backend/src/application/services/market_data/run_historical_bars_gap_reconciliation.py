"""Run low-frequency historical bars reconciliation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Callable

from application.services.market_data._bars_maintenance_support import (
    build_canonical_1m_rows,
    build_ready_state,
)
from application.services.market_data.run_ticker_bars_bootstrap import RunTickerBarsBootstrapService
from domain.entities import BarsMaintenanceResult, CanonicalBar, MarketDataMode
from domain.rules import MARKET_BARS_1M_RETENTION_TRADING_DAYS, MARKET_BARS_INITIALIZING_TIMEOUT_MINUTES
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _TimeRange:
    start_at: datetime
    end_at: datetime


@dataclass(slots=True)
class _DayRange:
    start_day: date
    end_day: date


class RunHistoricalBarsGapReconciliationService:
    """Backfill retained windows for tracked tickers."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        bars_client: MassiveBarsClient,
        calendar: UsStockCalendar,
        bootstrap_service: RunTickerBarsBootstrapService,
        mode: MarketDataMode,
        max_provider_calls_per_ticker: int = 8,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._bars_client = bars_client
        self._calendar = calendar
        self._bootstrap_service = bootstrap_service
        self._mode = mode
        self._max_provider_calls_per_ticker = max(1, max_provider_calls_per_ticker)
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self) -> BarsMaintenanceResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        timeout_before = effective_now - timedelta(minutes=MARKET_BARS_INITIALIZING_TIMEOUT_MINUTES)
        anchor_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(effective_now))
        minute_days = self._calendar.previous_trading_days(anchor_day, MARKET_BARS_1M_RETENTION_TRADING_DAYS)
        minute_start_at = self._calendar.session_window(minute_days[0], "pre_market").start_at
        minute_end_at = min(self._calendar.session_window(anchor_day, "after_hours").end_at, effective_now)
        daily_start_day = self._calendar.previous_trading_days(anchor_day, 90)[0]

        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()
            states = {state.ticker: state for state in await uow.ticker_bars_state.list_for_tickers(tickers=tickers)}

        bootstrap_tickers: list[str] = []
        reconcile_tickers: list[str] = []
        for ticker in tickers:
            state = states.get(ticker)
            if state is None or state.status in {"pending", "failed", "degraded"}:
                bootstrap_tickers.append(ticker)
                continue
            if (
                state.status == "initializing"
                and state.bootstrap_started_at is not None
                and state.bootstrap_started_at <= timeout_before
            ):
                bootstrap_tickers.append(ticker)
                continue
            if state.status == "ready":
                reconcile_tickers.append(ticker)

        processed_tickers = 0
        failed_tickers: list[str] = []
        for ticker in reconcile_tickers:
            try:
                await self._reconcile_ticker(
                    ticker=ticker,
                    minute_start_at=minute_start_at,
                    minute_end_at=minute_end_at,
                    daily_start_day=daily_start_day,
                    anchor_day=anchor_day,
                    effective_now=effective_now,
                )
            except Exception as exc:
                logger.warning("historical bars reconciliation failed", extra={"ticker": ticker})
                async with self._uow_factory.build() as uow:
                    await uow.ticker_bars_state.mark_degraded(
                        ticker=ticker,
                        degraded_at=self._now_provider().astimezone(UTC),
                        error_message=str(exc) or "historical bars reconciliation failed",
                    )
                    await uow.commit()
                failed_tickers.append(ticker)
                continue
            processed_tickers += 1

        bootstrap_result = await self._bootstrap_service.execute(tickers=bootstrap_tickers)
        return BarsMaintenanceResult(
            status="completed",
            total_tickers=len(tickers),
            processed_tickers=processed_tickers + bootstrap_result.refreshed_tickers,
            failed_tickers=failed_tickers + bootstrap_result.failed_tickers,
        )

    async def _reconcile_ticker(
        self,
        *,
        ticker: str,
        minute_start_at: datetime,
        minute_end_at: datetime,
        daily_start_day: date,
        anchor_day: date,
        effective_now: datetime,
    ) -> None:
        synced_at = self._now_provider().astimezone(UTC)
        completed_daily_end_day = self._completed_daily_end_day(anchor_day=anchor_day, effective_now=effective_now)
        async with self._uow_factory.build() as uow:
            existing_minute_rows = await uow.bars.list_1m(
                ticker=ticker,
                adjustment="split_adjusted",
                start_at=minute_start_at,
                end_at=minute_end_at,
                session_kind="regular",
            )
            existing_daily_rows = await uow.bars.list_1d(
                ticker=ticker,
                adjustment="split_adjusted",
                start_day=daily_start_day,
                end_day=completed_daily_end_day,
            )

        minute_ranges = self._find_missing_minute_ranges(
            existing_rows=existing_minute_rows,
            start_at=minute_start_at,
            end_at=minute_end_at,
            anchor_day=anchor_day,
            effective_now=effective_now,
        )
        daily_ranges = self._find_missing_daily_ranges(
            existing_rows=existing_daily_rows,
            start_day=daily_start_day,
            end_day=completed_daily_end_day,
        )
        minute_ranges, daily_ranges = self._apply_provider_call_budget(
            ticker=ticker,
            minute_ranges=minute_ranges,
            daily_ranges=daily_ranges,
        )

        minute_rows: list[CanonicalBar] = []
        for missing_range in minute_ranges:
            minute_provider_bars = await self._bars_client.fetch_range(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_value=str(int(missing_range.start_at.timestamp() * 1000)),
                to_value=str(int(missing_range.end_at.timestamp() * 1000)),
                adjusted=True,
            )
            minute_rows.extend(
                build_canonical_1m_rows(
                    ticker=ticker,
                    adjustment="split_adjusted",
                    provider_bars=minute_provider_bars,
                    calendar=self._calendar,
                    effective_now=effective_now,
                    synced_at=synced_at,
                )
            )
        minute_rows = [row for row in minute_rows if row.session_kind == "regular"]

        daily_rows: list[CanonicalBar] = []
        for missing_range in daily_ranges:
            daily_provider_bars = await self._bars_client.fetch_range(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_value=missing_range.start_day.isoformat(),
                to_value=missing_range.end_day.isoformat(),
                adjusted=True,
            )
            daily_rows.extend(self._to_daily_rows(ticker=ticker, provider_bars=daily_provider_bars, synced_at=synced_at))

        if not minute_rows and not daily_rows:
            return

        async with self._uow_factory.build() as uow:
            if minute_rows:
                await uow.bars.upsert_1m(minute_rows)
            if daily_rows:
                await uow.bars.upsert_1d(daily_rows)
            existing_state = await uow.ticker_bars_state.get_for_update(ticker=ticker)
            await uow.ticker_bars_state.upsert(
                build_ready_state(
                    ticker=ticker,
                    now=synced_at,
                    minute_rows=minute_rows,
                    daily_rows=daily_rows,
                    existing=existing_state,
                )
            )
            await uow.commit()

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

    def _completed_daily_end_day(self, *, anchor_day, effective_now: datetime):
        market_day = self._calendar.to_market_date(effective_now)
        if self._calendar.is_trading_day(market_day) and anchor_day == market_day:
            return self._calendar.previous_trading_day(anchor_day)
        return anchor_day

    def _find_missing_minute_ranges(
        self,
        *,
        existing_rows: list[CanonicalBar],
        start_at: datetime,
        end_at: datetime,
        anchor_day: date,
        effective_now: datetime,
    ) -> list[_TimeRange]:
        existing_starts = {row.bucket_start_at.astimezone(UTC) for row in existing_rows}
        expected_starts: list[datetime] = []
        for day in self._calendar.trading_days_between(
            self._calendar.to_market_date(start_at),
            self._calendar.to_market_date(end_at),
        ):
            expected_starts.extend(
                self._expected_minute_starts(
                    start_at=start_at,
                    end_at=end_at,
                    window_start_at=self._calendar.regular_session_window(day).start_at,
                    window_end_at=self._calendar.regular_session_window(day).end_at,
                    effective_now=effective_now,
                )
            )
        return self._missing_time_ranges(
            missing_starts=sorted(start for start in expected_starts if start not in existing_starts)
        )

    def _expected_minute_starts(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        window_start_at: datetime,
        window_end_at: datetime,
        effective_now: datetime,
    ) -> list[datetime]:
        lower_bound = max(start_at, window_start_at)
        upper_bound = min(end_at, window_end_at, effective_now)
        starts: list[datetime] = []
        current = lower_bound
        while current + timedelta(minutes=1) <= upper_bound:
            starts.append(current)
            current += timedelta(minutes=1)
        return starts

    def _missing_time_ranges(self, *, missing_starts: list[datetime]) -> list[_TimeRange]:
        if not missing_starts:
            return []
        ranges: list[_TimeRange] = []
        range_start = missing_starts[0]
        previous = missing_starts[0]
        for current in missing_starts[1:]:
            if current == previous + timedelta(minutes=1):
                previous = current
                continue
            ranges.append(_TimeRange(start_at=range_start, end_at=previous + timedelta(minutes=1)))
            range_start = current
            previous = current
        ranges.append(_TimeRange(start_at=range_start, end_at=previous + timedelta(minutes=1)))
        return ranges

    def _find_missing_daily_ranges(
        self,
        *,
        existing_rows: list[CanonicalBar],
        start_day: date,
        end_day: date,
    ) -> list[_DayRange]:
        existing_days = {row.trading_day for row in existing_rows}
        missing_days = [
            day for day in self._calendar.trading_days_between(start_day, end_day) if day not in existing_days
        ]
        if not missing_days:
            return []
        ranges: list[_DayRange] = []
        range_start = missing_days[0]
        previous = missing_days[0]
        for current in missing_days[1:]:
            if current == self._calendar.next_trading_day(previous):
                previous = current
                continue
            ranges.append(_DayRange(start_day=range_start, end_day=previous))
            range_start = current
            previous = current
        ranges.append(_DayRange(start_day=range_start, end_day=previous))
        return ranges

    def _apply_provider_call_budget(
        self,
        *,
        ticker: str,
        minute_ranges: list[_TimeRange],
        daily_ranges: list[_DayRange],
    ) -> tuple[list[_TimeRange], list[_DayRange]]:
        total_ranges = len(minute_ranges) + len(daily_ranges)
        if total_ranges <= self._max_provider_calls_per_ticker:
            return minute_ranges, daily_ranges

        minute_budget = min(len(minute_ranges), self._max_provider_calls_per_ticker)
        daily_budget = self._max_provider_calls_per_ticker - minute_budget
        logger.warning(
            "historical bars gap reconciliation provider call budget reached",
            extra={
                "ticker": ticker,
                "max_provider_calls_per_ticker": self._max_provider_calls_per_ticker,
                "minute_ranges": len(minute_ranges),
                "daily_ranges": len(daily_ranges),
                "deferred_ranges": total_ranges - self._max_provider_calls_per_ticker,
            },
        )
        return minute_ranges[:minute_budget], daily_ranges[:daily_budget]
