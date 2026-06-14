"""Run retention cleanup for canonical bars storage."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Callable

from application.services.market_data._bars_maintenance_support import (
    clamp_state_to_regular_1m_bounds,
    clamp_state_to_retention,
)
from domain.entities import BarsMaintenanceResult, MarketDataMode
from domain.rules import (
    MARKET_BARS_1D_RETENTION_YEARS,
    MARKET_BARS_1M_RETENTION_TRADING_DAYS,
    TICKER_BARS_READINESS_STATES,
)
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory


LEGACY_EXTENDED_SESSION_KINDS = ("after_hours", "pre_market")


class RunBarsRetentionCleanupService:
    """Delete bars outside the retained MVP windows."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        calendar: UsStockCalendar,
        mode: MarketDataMode,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._calendar = calendar
        self._mode = mode
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self) -> BarsMaintenanceResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        anchor_day = self._calendar.previous_or_same_trading_day(self._calendar.to_market_date(effective_now))
        minute_threshold_day = self._calendar.previous_trading_days(
            anchor_day,
            MARKET_BARS_1M_RETENTION_TRADING_DAYS,
        )[0]
        daily_threshold_day = self._subtract_years(anchor_day, MARKET_BARS_1D_RETENTION_YEARS)

        async with self._uow_factory.build() as uow:
            deleted_1m_rows = await uow.bars.delete_1m_before(threshold_day=minute_threshold_day)
            deleted_1m_rows += await uow.bars.delete_1m_by_session_kinds(
                session_kinds=list(LEGACY_EXTENDED_SESSION_KINDS),
            )
            deleted_1d_rows = await uow.bars.delete_1d_before(threshold_day=daily_threshold_day)
            states = await uow.ticker_bars_state.list_by_statuses(
                statuses=sorted(TICKER_BARS_READINESS_STATES)
            )
            for state in states:
                current_state = await uow.ticker_bars_state.get_for_update(ticker=state.ticker)
                if current_state is None or current_state.status not in TICKER_BARS_READINESS_STATES:
                    continue
                retained_state = clamp_state_to_retention(
                    state=current_state,
                    minute_threshold_day=minute_threshold_day,
                    daily_threshold_day=daily_threshold_day,
                    now=effective_now,
                )
                regular_1m_bounds = await uow.bars.get_regular_1m_bounds(ticker=state.ticker)
                await uow.ticker_bars_state.upsert(
                    clamp_state_to_regular_1m_bounds(
                        state=retained_state,
                        regular_bounds=regular_1m_bounds,
                        now=effective_now,
                    )
                )
            await uow.commit()

        return BarsMaintenanceResult(
            status="completed",
            deleted_1m_rows=deleted_1m_rows,
            deleted_1d_rows=deleted_1d_rows,
        )

    def _subtract_years(self, value: date, years: int) -> date:
        try:
            return value.replace(year=value.year - years)
        except ValueError:
            return value.replace(month=2, day=28, year=value.year - years)
