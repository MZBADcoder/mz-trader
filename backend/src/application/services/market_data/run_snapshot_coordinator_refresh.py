"""Run snapshot coordinator refresh use case."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from domain.entities import MarketDataMode, SnapshotCoordinatorRefreshResult
from domain.exceptions import MarketSnapshotUpstreamUnavailableError
from infrastructure.cache import RedisSnapshotStore
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
        mode: MarketDataMode,
        batch_size: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._snapshot_store = snapshot_store
        self._snapshot_client = snapshot_client
        self._mode = mode
        self._batch_size = batch_size

    async def execute(self) -> SnapshotCoordinatorRefreshResult:
        async with self._uow_factory.build() as uow:
            tickers = await uow.watchlist.list_distinct_tickers()

        logger.info("snapshot coordinator refresh started", extra={"ticker_count": len(tickers)})

        if not tickers:
            return SnapshotCoordinatorRefreshResult(total_tickers=0, refreshed_tickers=0, failed_tickers=[])

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

            await self._snapshot_store.set_many(batch.snapshots)
            refreshed_tickers += len(batch.snapshots)

            if batch.unresolved_tickers:
                failed_tickers.extend(batch.unresolved_tickers)
                logger.warning(
                    "snapshot coordinator batch partially resolved",
                    extra={
                        "ticker_count": len(chunk),
                        "refreshed_tickers": len(batch.snapshots),
                        "failed_tickers": batch.unresolved_tickers,
                    },
                )
            else:
                logger.info(
                    "snapshot coordinator batch completed",
                    extra={"ticker_count": len(chunk), "refreshed_tickers": len(batch.snapshots)},
                )

        return SnapshotCoordinatorRefreshResult(
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
