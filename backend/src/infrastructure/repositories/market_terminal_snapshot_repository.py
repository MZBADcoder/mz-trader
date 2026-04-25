"""Terminal market snapshot repository implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import Snapshot
from infrastructure.db.mappers import to_market_terminal_snapshot_entity
from infrastructure.db.models import MarketTerminalSnapshotModel


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class MarketTerminalSnapshotRepository:
    """Persist terminal daily snapshots captured after after-hours close."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_tickers(
        self,
        *,
        tickers: list[str],
        trading_day: date,
    ) -> list[Snapshot]:
        if not tickers:
            return []

        stmt = (
            select(MarketTerminalSnapshotModel)
            .where(
                MarketTerminalSnapshotModel.ticker.in_(tickers),
                MarketTerminalSnapshotModel.trading_day == trading_day,
            )
            .order_by(MarketTerminalSnapshotModel.ticker.asc())
        )
        result = await self._session.scalars(stmt)
        return [to_market_terminal_snapshot_entity(model) for model in result.all()]

    async def upsert_many(self, *, snapshots: list[Snapshot], captured_at: datetime) -> None:
        if not snapshots:
            return

        values = [
            {
                "id": uuid.uuid4(),
                "ticker": snapshot.ticker,
                "trading_day": snapshot.trading_day,
                "last": snapshot.last,
                "regular_close": snapshot.regular_close,
                "change": snapshot.change,
                "change_pct": snapshot.change_pct,
                "open": snapshot.open,
                "high": snapshot.high,
                "low": snapshot.low,
                "volume": snapshot.volume,
                "prev_close": snapshot.prev_close,
                "market_status": snapshot.market_status,
                "session": snapshot.session,
                "last_session": snapshot.last_session,
                "last_trade_at": _ensure_utc(snapshot.last_trade_at) if snapshot.last_trade_at else None,
                "delay_minutes": snapshot.delay_minutes,
                "is_realtime": snapshot.is_realtime,
                "provider_updated_at": _ensure_utc(snapshot.provider_updated_at),
                "fetched_at": _ensure_utc(snapshot.fetched_at),
                "data_source": snapshot.data_source,
                "captured_at": _ensure_utc(captured_at),
            }
            for snapshot in snapshots
            if snapshot.trading_day is not None
        ]
        if not values:
            return

        stmt = insert(MarketTerminalSnapshotModel).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_market_terminal_snapshots_ticker_trading_day",
            set_={
                "last": stmt.excluded.last,
                "regular_close": stmt.excluded.regular_close,
                "change": stmt.excluded.change,
                "change_pct": stmt.excluded.change_pct,
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "volume": stmt.excluded.volume,
                "prev_close": stmt.excluded.prev_close,
                "market_status": stmt.excluded.market_status,
                "session": stmt.excluded.session,
                "last_session": stmt.excluded.last_session,
                "last_trade_at": stmt.excluded.last_trade_at,
                "delay_minutes": stmt.excluded.delay_minutes,
                "is_realtime": stmt.excluded.is_realtime,
                "provider_updated_at": stmt.excluded.provider_updated_at,
                "fetched_at": stmt.excluded.fetched_at,
                "data_source": stmt.excluded.data_source,
                "captured_at": stmt.excluded.captured_at,
            },
        )
        await self._session.execute(stmt)
