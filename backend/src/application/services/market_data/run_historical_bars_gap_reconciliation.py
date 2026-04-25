"""Run low-frequency historical bars reconciliation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Callable

from application.services.market_data._bars_maintenance_support import (
    build_canonical_1m_rows,
    build_ready_state,
    retain_latest_extended_session_rows,
)
from application.services.market_data.run_ticker_bars_bootstrap import RunTickerBarsBootstrapService
from domain.entities import BarsMaintenanceResult, CanonicalBar, MarketDataMode
from domain.rules import MARKET_BARS_1M_RETENTION_TRADING_DAYS
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient


logger = logging.getLogger(__name__)


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
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._bars_client = bars_client
        self._calendar = calendar
        self._bootstrap_service = bootstrap_service
        self._mode = mode
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self) -> BarsMaintenanceResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        anchor_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(effective_now))
        minute_days = self._calendar.previous_trading_days(anchor_day, MARKET_BARS_1M_RETENTION_TRADING_DAYS)
        minute_start_at = self._calendar.session_window(minute_days[0], "pre_market").start_at
        minute_end_at = min(self._calendar.session_window(anchor_day, "after_hours").end_at, effective_now)
        daily_start_day = self._calendar.previous_trading_days(anchor_day, 90)[0]

        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()
            states = {state.ticker: state for state in await uow.ticker_bars_state.list_for_tickers(tickers=tickers)}

        bootstrap_tickers = [ticker for ticker in tickers if states.get(ticker) is None or states[ticker].status != "ready"]
        reconcile_tickers = [ticker for ticker in tickers if ticker not in bootstrap_tickers]

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
        daily_start_day,
        anchor_day,
        effective_now: datetime,
    ) -> None:
        synced_at = self._now_provider().astimezone(UTC)
        minute_provider_bars = await self._bars_client.fetch_range(
            ticker=ticker,
            multiplier=1,
            timespan="minute",
            from_value=str(int(minute_start_at.timestamp() * 1000)),
            to_value=str(int(minute_end_at.timestamp() * 1000)),
            adjusted=True,
        )
        minute_rows = build_canonical_1m_rows(
            ticker=ticker,
            adjustment="split_adjusted",
            provider_bars=minute_provider_bars,
            calendar=self._calendar,
            effective_now=effective_now,
            synced_at=synced_at,
        )
        minute_rows = retain_latest_extended_session_rows(
            rows=minute_rows,
            latest_extended_trading_day=anchor_day,
        )
        daily_provider_bars = await self._bars_client.fetch_range(
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_value=daily_start_day.isoformat(),
            to_value=self._completed_daily_end_day(anchor_day=anchor_day, effective_now=effective_now).isoformat(),
            adjusted=True,
        )
        daily_rows = self._to_daily_rows(ticker=ticker, provider_bars=daily_provider_bars, synced_at=synced_at)
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
