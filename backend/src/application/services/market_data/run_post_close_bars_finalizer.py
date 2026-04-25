"""Run post-close bar finalization use case."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Callable

from application.services.market_data._bars_maintenance_support import (
    aggregate_daily_row,
    build_canonical_1m_rows,
    build_ready_state,
)
from domain.entities import MarketDataMode, SnapshotCoordinatorRefreshResult
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveBarsClient


logger = logging.getLogger(__name__)


class RunPostCloseBarsFinalizerService:
    """Finalize completed regular daily bars after market close."""

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

        regular_window = self._calendar.regular_session_window(trading_day)
        if effective_now < regular_window.end_at:
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="regular_session_not_closed",
            )

        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()
            states = {state.ticker: state for state in await uow.ticker_bars_state.list_for_tickers(tickers=tickers)}

        finalized_tickers = 0
        failed_tickers: list[str] = []
        for ticker in tickers:
            state = states.get(ticker)
            if state is None or state.status not in {"ready", "degraded"}:
                continue
            try:
                provider_bars = await self._bars_client.fetch_range(
                    ticker=ticker,
                    multiplier=1,
                    timespan="minute",
                    from_value=str(int(regular_window.start_at.timestamp() * 1000)),
                    to_value=str(int(regular_window.end_at.timestamp() * 1000)),
                    adjusted=True,
                )
            except Exception:
                logger.warning("post-close finalizer failed", extra={"ticker": ticker})
                async with self._uow_factory.build() as uow:
                    await uow.ticker_bars_state.mark_degraded(
                        ticker=ticker,
                        degraded_at=self._now_provider().astimezone(UTC),
                        error_message="post-close finalizer failed",
                    )
                    await uow.commit()
                failed_tickers.append(ticker)
                continue

            now_synced_at = self._now_provider().astimezone(UTC)
            minute_rows = build_canonical_1m_rows(
                ticker=ticker,
                provider_bars=provider_bars,
                adjustment="split_adjusted",
                calendar=self._calendar,
                effective_now=effective_now,
                synced_at=now_synced_at,
            )
            if not minute_rows:
                continue

            regular_rows = [row for row in minute_rows if row.session_kind == "regular" and row.trading_day == trading_day]
            if not regular_rows:
                continue
            daily_row = aggregate_daily_row(
                ticker=ticker,
                adjustment="split_adjusted",
                trading_day=trading_day,
                rows=regular_rows,
                bucket_start_at=regular_window.start_at,
                synced_at=now_synced_at,
            )
            async with self._uow_factory.build() as uow:
                await uow.bars.upsert_1m(minute_rows)
                await uow.bars.upsert_1d([daily_row])
                existing_state = await uow.ticker_bars_state.get_for_update(ticker=ticker)
                await uow.ticker_bars_state.upsert(
                    build_ready_state(
                        ticker=ticker,
                        now=now_synced_at,
                        minute_rows=minute_rows,
                        daily_rows=[daily_row],
                        existing=existing_state,
                    )
                )
                await uow.commit()
            finalized_tickers += 1

        return SnapshotCoordinatorRefreshResult(
            status="completed",
            total_tickers=len(tickers),
            refreshed_tickers=finalized_tickers,
            failed_tickers=failed_tickers,
        )
