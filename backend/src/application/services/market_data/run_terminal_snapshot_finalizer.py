"""Run terminal snapshot finalization after after-hours close."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Callable

from application.services.market_data._snapshot_session_support import (
    attach_snapshot_session_context,
    build_snapshot_session_context,
)
from domain.entities import MarketDataMode, SnapshotCoordinatorRefreshResult
from domain.exceptions import MarketSnapshotUpstreamUnavailableError
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveSnapshotClient


logger = logging.getLogger(__name__)


class RunTerminalSnapshotFinalizerService:
    """Capture one terminal snapshot per ticker after after-hours close."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        snapshot_client: MassiveSnapshotClient,
        calendar: UsStockCalendar,
        mode: MarketDataMode,
        batch_size: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._snapshot_client = snapshot_client
        self._calendar = calendar
        self._mode = mode
        self._batch_size = batch_size
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self) -> SnapshotCoordinatorRefreshResult:
        now = self._now_provider().astimezone(UTC)
        effective_now = now - timedelta(minutes=self._mode.delay_minutes)
        market_day = self._calendar.to_market_date(effective_now)
        if not self._calendar.is_trading_day(market_day):
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="not_trading_day",
            )

        after_window = self._calendar.session_window(market_day, "after_hours")
        if effective_now <= after_window.end_at:
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="after_hours_not_closed",
            )

        context = build_snapshot_session_context(calendar=self._calendar, effective_now=effective_now)
        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()

        refreshed_tickers = 0
        failed_tickers: list[str] = []
        for chunk in self._chunked(tickers, self._batch_size):
            try:
                batch = await self._snapshot_client.fetch_snapshots(
                    tickers=chunk,
                    mode=self._mode,
                    data_source="massive_terminal_snapshot_finalizer",
                )
            except MarketSnapshotUpstreamUnavailableError:
                failed_tickers.extend(chunk)
                logger.warning(
                    "terminal snapshot finalizer batch failed",
                    extra={"ticker_count": len(chunk), "failed_tickers": chunk},
                )
                continue

            snapshots = [
                attach_snapshot_session_context(
                    snapshot=snapshot,
                    context=context,
                    calendar=self._calendar,
                )
                for snapshot in batch.snapshots
            ]
            async with self._uow_factory.build() as uow:
                await uow.terminal_snapshots.upsert_many(snapshots=snapshots, captured_at=now)
                await uow.commit()

            refreshed_tickers += len(snapshots)
            failed_tickers.extend(batch.unresolved_tickers)

        return SnapshotCoordinatorRefreshResult(
            status="completed",
            total_tickers=len(tickers),
            refreshed_tickers=refreshed_tickers,
            failed_tickers=self._dedupe(failed_tickers),
        )

    def _chunked(self, tickers: list[str], chunk_size: int) -> Iterable[list[str]]:
        for index in range(0, len(tickers), chunk_size):
            yield tickers[index : index + chunk_size]

    def _dedupe(self, tickers: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for ticker in tickers:
            if ticker in seen:
                continue
            deduped.append(ticker)
            seen.add(ticker)
        return deduped
