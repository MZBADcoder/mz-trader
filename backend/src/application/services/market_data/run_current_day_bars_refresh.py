"""Run current-day bar refresh use case."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Callable

from application.services.market_data._bars_maintenance_support import build_canonical_1m_rows, build_ready_state
from domain.entities import MarketDataMode, SnapshotCoordinatorRefreshResult
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient


logger = logging.getLogger(__name__)


class RunCurrentDayBarsRefreshService:
    """Refresh current-day minute bars for active watchlist tickers."""

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

    async def execute(self) -> SnapshotCoordinatorRefreshResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        trading_day = self._calendar.to_market_date(effective_now)
        if not self._calendar.is_trading_day(trading_day):
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="not_trading_day",
            )

        pre_window = self._calendar.session_window(trading_day, "pre_market")
        after_window = self._calendar.session_window(trading_day, "after_hours")
        if effective_now <= pre_window.start_at or effective_now > after_window.end_at:
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="outside_refresh_window",
            )

        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()
            states = {state.ticker: state for state in await uow.ticker_bars_state.list_for_tickers(tickers=tickers)}

        refreshed_tickers = 0
        failed_tickers: list[str] = []
        for ticker in tickers:
            state = states.get(ticker)
            if state is not None and state.status not in {"ready", "degraded"}:
                continue
            try:
                fetch_start = max(pre_window.start_at, effective_now - timedelta(minutes=10))
                provider_bars = await self._bars_client.fetch_range(
                    ticker=ticker,
                    multiplier=1,
                    timespan="minute",
                    from_value=str(int(fetch_start.timestamp() * 1000)),
                    to_value=str(int(min(after_window.end_at, effective_now).timestamp() * 1000)),
                    adjusted=True,
                )
            except Exception:
                logger.warning("current-day bars refresh failed", extra={"ticker": ticker})
                failed_tickers.append(ticker)
                continue

            now_synced_at = self._now_provider().astimezone(UTC)
            canonical_rows = build_canonical_1m_rows(
                ticker=ticker,
                provider_bars=provider_bars,
                adjustment="split_adjusted",
                calendar=self._calendar,
                effective_now=effective_now,
                synced_at=now_synced_at,
            )
            if not canonical_rows:
                continue
            async with self._uow_factory.build() as uow:
                await uow.bars.upsert_1m(canonical_rows)
                existing_state = await uow.ticker_bars_state.get(ticker=ticker)
                await uow.ticker_bars_state.upsert(
                    build_ready_state(
                        ticker=ticker,
                        now=now_synced_at,
                        minute_rows=canonical_rows,
                        daily_rows=[],
                        existing=existing_state,
                    )
                )
                await uow.commit()
            refreshed_tickers += 1

        return SnapshotCoordinatorRefreshResult(
            status="completed",
            total_tickers=len(tickers),
            refreshed_tickers=refreshed_tickers,
            failed_tickers=failed_tickers,
        )
