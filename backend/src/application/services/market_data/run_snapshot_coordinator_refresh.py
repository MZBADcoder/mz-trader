"""Run snapshot coordinator refresh use case."""

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
from infrastructure.cache import RedisSnapshotStore
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveSnapshotClient


logger = logging.getLogger(__name__)


class RunSnapshotCoordinatorRefreshService:
    """Refresh Redis snapshots for all distinct watchlist tickers."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        snapshot_store: RedisSnapshotStore,
        snapshot_client: MassiveSnapshotClient,
        calendar: UsStockCalendar,
        mode: MarketDataMode,
        batch_size: int,
        refresh_lock_ttl_seconds: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._snapshot_store = snapshot_store
        self._snapshot_client = snapshot_client
        self._calendar = calendar
        self._mode = mode
        self._batch_size = batch_size
        self._refresh_lock_ttl_seconds = refresh_lock_ttl_seconds
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self) -> SnapshotCoordinatorRefreshResult:
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        context = build_snapshot_session_context(calendar=self._calendar, effective_now=effective_now)
        if not context.active:
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="outside_snapshot_refresh_window",
            )

        lock_token = await self._snapshot_store.acquire_refresh_lock(
            ttl_seconds=self._refresh_lock_ttl_seconds
        )
        if lock_token is None:
            return SnapshotCoordinatorRefreshResult(
                status="skipped",
                total_tickers=0,
                refreshed_tickers=0,
                failed_tickers=[],
                skip_reason="lock_not_acquired",
            )

        try:
            async with self._uow_factory.build() as uow:
                tickers = await uow.watchlist.list_distinct_tickers()

            logger.info("snapshot coordinator refresh started", extra={"ticker_count": len(tickers)})

            if not tickers:
                return SnapshotCoordinatorRefreshResult(
                    status="completed",
                    total_tickers=0,
                    refreshed_tickers=0,
                    failed_tickers=[],
                )

            refreshed_tickers = 0
            failed_tickers: list[str] = []

            for chunk in self._chunked(tickers, self._batch_size):
                try:
                    batch = await self._snapshot_client.fetch_snapshots(
                        tickers=chunk,
                        mode=self._mode,
                        data_source="massive_coordinator",
                    )
                except MarketSnapshotUpstreamUnavailableError:
                    failed_tickers.extend(chunk)
                    logger.warning(
                        "snapshot coordinator batch failed",
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
                await self._snapshot_store.set_many(snapshots)
                refreshed_tickers += len(snapshots)

                if batch.unresolved_tickers:
                    failed_tickers.extend(batch.unresolved_tickers)
                    logger.warning(
                        "snapshot coordinator batch partially resolved",
                        extra={
                            "ticker_count": len(chunk),
                            "refreshed_tickers": len(snapshots),
                            "failed_tickers": batch.unresolved_tickers,
                        },
                    )
                else:
                    logger.info(
                        "snapshot coordinator batch completed",
                        extra={"ticker_count": len(chunk), "refreshed_tickers": len(snapshots)},
                    )

            return SnapshotCoordinatorRefreshResult(
                status="completed",
                total_tickers=len(tickers),
                refreshed_tickers=refreshed_tickers,
                failed_tickers=self._dedupe(failed_tickers),
            )
        finally:
            await self._snapshot_store.release_refresh_lock(lock_token)

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

    def set_now_provider(self, now_provider: Callable[[], datetime]) -> None:
        """Override the clock used by this service."""
        self._now_provider = now_provider
