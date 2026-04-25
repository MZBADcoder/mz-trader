"""Get batch snapshots use case."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Callable

from application.services.market_data._snapshot_session_support import (
    SnapshotSessionContext,
    attach_snapshot_session_context,
    build_snapshot_session_context,
)
from bootstrap.request_context import bind_request_context
from domain.entities import BatchSnapshotsResult, MarketDataMode, Snapshot
from domain.exceptions import MarketSnapshotUpstreamUnavailableError
from domain.rules import validate_market_data_tickers
from infrastructure.cache import RedisSnapshotStore
from infrastructure.calendar import UsStockCalendar
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveSnapshotClient


logger = logging.getLogger(__name__)


class GetBatchSnapshotsService:
    """Resolve snapshots from Redis first, then fallback to Massive."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        snapshot_store: RedisSnapshotStore,
        snapshot_client: MassiveSnapshotClient,
        calendar: UsStockCalendar,
        mode: MarketDataMode,
        request_limit: int,
        batch_size: int,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._snapshot_store = snapshot_store
        self._snapshot_client = snapshot_client
        self._calendar = calendar
        self._mode = mode
        self._request_limit = request_limit
        self._batch_size = batch_size
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    async def execute(self, *, user_id: str, tickers: list[str]) -> BatchSnapshotsResult:
        bind_request_context(user_id=user_id)

        normalized_tickers = validate_market_data_tickers(tickers, limit=self._request_limit)
        effective_now = self._now_provider().astimezone(UTC) - timedelta(minutes=self._mode.delay_minutes)
        context = build_snapshot_session_context(calendar=self._calendar, effective_now=effective_now)
        if not context.active:
            return await self._execute_from_terminal_snapshots(tickers=normalized_tickers, context=context)

        cached_snapshots = await self._snapshot_store.get_many(normalized_tickers)
        cached_snapshots = {
            ticker: self._with_session_context(snapshot=snapshot, context=context)
            for ticker, snapshot in cached_snapshots.items()
        }

        missing_tickers = [ticker for ticker in normalized_tickers if ticker not in cached_snapshots]
        fallback_snapshots: dict[str, Snapshot] = {}
        unresolved_tickers: list[str] = []

        if missing_tickers:
            fallback_snapshots, unresolved_tickers = await self._fetch_missing_snapshots(
                missing_tickers,
                context=context,
            )
            await self._snapshot_store.set_many(list(fallback_snapshots.values()))

        snapshots_by_ticker = {**cached_snapshots, **fallback_snapshots}
        items = [snapshots_by_ticker[ticker] for ticker in normalized_tickers if ticker in snapshots_by_ticker]

        if not items:
            raise MarketSnapshotUpstreamUnavailableError(
                detail="No snapshots could be resolved for the requested tickers."
            )

        if unresolved_tickers:
            logger.warning(
                "partial snapshot response",
                extra={
                    "ticker_count": len(normalized_tickers),
                    "redis_hit_count": len(cached_snapshots),
                    "redis_miss_count": len(missing_tickers),
                    "redis_miss_tickers": missing_tickers,
                    "unresolved_tickers": unresolved_tickers,
                    "returned_tickers": [snapshot.ticker for snapshot in items],
                },
            )
        else:
            logger.info(
                "snapshot request resolved",
                extra={
                    "ticker_count": len(normalized_tickers),
                    "redis_hit_count": len(cached_snapshots),
                    "redis_miss_count": len(missing_tickers),
                },
            )

        return BatchSnapshotsResult(
            items=items,
            delay_minutes=self._mode.delay_minutes,
            is_realtime=self._mode.is_realtime,
        )

    async def _fetch_missing_snapshots(
        self,
        tickers: list[str],
        *,
        context: SnapshotSessionContext,
    ) -> tuple[dict[str, Snapshot], list[str]]:
        snapshots_by_ticker: dict[str, Snapshot] = {}
        unresolved_tickers: list[str] = []

        for chunk in self._chunked(tickers, self._batch_size):
            try:
                batch = await self._snapshot_client.fetch_snapshots(
                    tickers=chunk,
                    mode=self._mode,
                    data_source="massive_fallback",
                )
            except MarketSnapshotUpstreamUnavailableError:
                unresolved_tickers.extend(chunk)
                logger.warning(
                    "snapshot fallback batch failed",
                    extra={"ticker_count": len(chunk), "failed_tickers": chunk},
                )
                continue

            for snapshot in batch.snapshots:
                snapshots_by_ticker[snapshot.ticker] = self._with_session_context(
                    snapshot=snapshot,
                    context=context,
                )
            unresolved_tickers.extend(batch.unresolved_tickers)

        return snapshots_by_ticker, self._dedupe(unresolved_tickers)

    async def _execute_from_terminal_snapshots(
        self,
        *,
        tickers: list[str],
        context: SnapshotSessionContext,
    ) -> BatchSnapshotsResult:
        async with self._uow_factory.build() as uow:
            terminal_snapshots = await uow.terminal_snapshots.list_for_tickers(
                tickers=tickers,
                trading_day=context.trading_day,
            )

        snapshots_by_ticker = {
            snapshot.ticker: replace(snapshot, session=context.session) for snapshot in terminal_snapshots
        }
        items = [snapshots_by_ticker[ticker] for ticker in tickers if ticker in snapshots_by_ticker]
        if not items:
            raise MarketSnapshotUpstreamUnavailableError(
                detail="No terminal snapshots could be resolved for the requested tickers."
            )

        missing_tickers = [ticker for ticker in tickers if ticker not in snapshots_by_ticker]
        if missing_tickers:
            logger.warning(
                "partial terminal snapshot response",
                extra={
                    "ticker_count": len(tickers),
                    "trading_day": context.trading_day.isoformat(),
                    "missing_tickers": missing_tickers,
                    "returned_tickers": [snapshot.ticker for snapshot in items],
                },
            )

        return BatchSnapshotsResult(
            items=items,
            delay_minutes=self._mode.delay_minutes,
            is_realtime=self._mode.is_realtime,
        )

    def _with_session_context(self, *, snapshot: Snapshot, context: SnapshotSessionContext) -> Snapshot:
        return attach_snapshot_session_context(
            snapshot=snapshot,
            context=context,
            calendar=self._calendar,
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
