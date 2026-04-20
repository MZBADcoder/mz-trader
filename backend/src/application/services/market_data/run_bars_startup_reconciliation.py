"""Run startup reconciliation for ticker bars state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

from domain.entities import BarsMaintenanceResult, MarketDataMode
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory

from application.services.market_data.run_ticker_bars_bootstrap import RunTickerBarsBootstrapService


class RunBarsStartupReconciliationService:
    """Reconcile ticker bars state after process startup."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        bootstrap_service: RunTickerBarsBootstrapService,
        mode: MarketDataMode,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._bootstrap_service = bootstrap_service
        self._mode = mode
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self) -> BarsMaintenanceResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        timeout_before = effective_now - timedelta(minutes=30)
        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()
            states = {state.ticker: state for state in await uow.ticker_bars_state.list_for_tickers(tickers=tickers)}
            target_tickers: list[str] = []
            for ticker in tickers:
                state = states.get(ticker)
                if state is None:
                    await uow.ticker_bars_state.ensure_pending(ticker=ticker, requested_at=effective_now)
                    target_tickers.append(ticker)
                    continue
                if state.status == "initializing" and state.bootstrap_started_at is not None and state.bootstrap_started_at <= timeout_before:
                    await uow.ticker_bars_state.mark_degraded(
                        ticker=ticker,
                        degraded_at=effective_now,
                        error_message="bootstrap initialization timed out before startup reconciliation completed.",
                    )
                    target_tickers.append(ticker)
                    continue
                if state.status in {"pending", "failed", "degraded"}:
                    target_tickers.append(ticker)
            await uow.commit()

        bootstrap_result = await self._bootstrap_service.execute(tickers=target_tickers)
        return BarsMaintenanceResult(
            status="completed",
            total_tickers=len(tickers),
            processed_tickers=bootstrap_result.refreshed_tickers,
            failed_tickers=bootstrap_result.failed_tickers,
        )
