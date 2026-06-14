"""Market bar repository implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import Select, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import CanonicalBar
from infrastructure.db.mappers import to_market_bar_1d_entity, to_market_bar_1m_entity
from infrastructure.db.models import MarketBar1dModel, MarketBar1mModel


MARKET_BAR_UPSERT_BATCH_SIZE = 1_000


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _chunk_bars(bars: list[CanonicalBar]) -> list[list[CanonicalBar]]:
    return [
        bars[start : start + MARKET_BAR_UPSERT_BATCH_SIZE]
        for start in range(0, len(bars), MARKET_BAR_UPSERT_BATCH_SIZE)
    ]


class MarketBarRepository:
    """Persist and query canonical market bars."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_1m(
        self,
        *,
        ticker: str,
        adjustment: str,
        start_at: datetime,
        end_at: datetime,
        session_kind: str | None = None,
    ) -> list[CanonicalBar]:
        stmt: Select[tuple[MarketBar1mModel]] = (
            select(MarketBar1mModel)
            .where(
                MarketBar1mModel.ticker == ticker,
                MarketBar1mModel.adjustment == adjustment,
                MarketBar1mModel.bucket_start_at_utc >= _ensure_utc(start_at),
                MarketBar1mModel.bucket_start_at_utc < _ensure_utc(end_at),
            )
            .order_by(MarketBar1mModel.bucket_start_at_utc.asc())
        )
        if session_kind is not None:
            stmt = stmt.where(MarketBar1mModel.session_kind == session_kind)
        result = await self._session.scalars(stmt)
        return [to_market_bar_1m_entity(model) for model in result.all()]

    async def list_1d(
        self,
        *,
        ticker: str,
        adjustment: str,
        start_day: date,
        end_day: date,
    ) -> list[CanonicalBar]:
        stmt = (
            select(MarketBar1dModel)
            .where(
                MarketBar1dModel.ticker == ticker,
                MarketBar1dModel.adjustment == adjustment,
                MarketBar1dModel.trading_day >= start_day,
                MarketBar1dModel.trading_day <= end_day,
            )
            .order_by(MarketBar1dModel.trading_day.asc())
        )
        result = await self._session.scalars(stmt)
        return [to_market_bar_1d_entity(model) for model in result.all()]

    async def get_latest_1m(
        self,
        *,
        ticker: str,
        adjustment: str,
        trading_day: date,
        session_kind: str | None = None,
    ) -> CanonicalBar | None:
        stmt = (
            select(MarketBar1mModel)
            .where(
                MarketBar1mModel.ticker == ticker,
                MarketBar1mModel.adjustment == adjustment,
                MarketBar1mModel.trading_day == trading_day,
            )
            .order_by(MarketBar1mModel.bucket_start_at_utc.desc())
            .limit(1)
        )
        if session_kind is not None:
            stmt = stmt.where(MarketBar1mModel.session_kind == session_kind)
        model = await self._session.scalar(stmt)
        return to_market_bar_1m_entity(model) if model is not None else None

    async def get_regular_1m_bounds(self, *, ticker: str) -> tuple[date, date, datetime] | None:
        stmt = select(
            func.min(MarketBar1mModel.trading_day),
            func.max(MarketBar1mModel.trading_day),
            func.max(MarketBar1mModel.bucket_start_at_utc),
        ).where(
            MarketBar1mModel.ticker == ticker,
            MarketBar1mModel.session_kind == "regular",
        )
        earliest_day, latest_day, latest_bucket = (await self._session.execute(stmt)).one()
        if earliest_day is None or latest_day is None or latest_bucket is None:
            return None
        return earliest_day, latest_day, _ensure_utc(latest_bucket)

    async def upsert_1m(self, bars: list[CanonicalBar]) -> None:
        for batch in _chunk_bars(bars):
            await self._upsert_1m_batch(batch)

    async def _upsert_1m_batch(self, bars: list[CanonicalBar]) -> None:
        values = [
            {
                "id": uuid.uuid4(),
                "ticker": bar.ticker,
                "adjustment": bar.adjustment,
                "bucket_start_at_utc": _ensure_utc(bar.bucket_start_at),
                "trading_day": bar.trading_day,
                "session_kind": bar.session_kind,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vw": bar.vw,
                "trade_count": bar.trade_count,
                "provider_updated_at": _ensure_utc(bar.provider_updated_at),
                "is_final": bar.is_final,
                "first_synced_at": _ensure_utc(bar.first_synced_at),
                "last_synced_at": _ensure_utc(bar.last_synced_at),
            }
            for bar in bars
        ]
        stmt = insert(MarketBar1mModel).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_market_bars_1m_ticker_adjustment_bucket_start_at_utc",
            set_={
                "trading_day": stmt.excluded.trading_day,
                "session_kind": stmt.excluded.session_kind,
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "vw": stmt.excluded.vw,
                "trade_count": stmt.excluded.trade_count,
                "provider_updated_at": stmt.excluded.provider_updated_at,
                "is_final": stmt.excluded.is_final,
                "last_synced_at": stmt.excluded.last_synced_at,
            },
        )
        await self._session.execute(stmt)

    async def upsert_1d(self, bars: list[CanonicalBar]) -> None:
        for batch in _chunk_bars(bars):
            await self._upsert_1d_batch(batch)

    async def _upsert_1d_batch(self, bars: list[CanonicalBar]) -> None:
        values = [
            {
                "id": uuid.uuid4(),
                "ticker": bar.ticker,
                "adjustment": bar.adjustment,
                "trading_day": bar.trading_day,
                "bucket_start_at_utc": _ensure_utc(bar.bucket_start_at),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vw": bar.vw,
                "trade_count": bar.trade_count,
                "provider_updated_at": _ensure_utc(bar.provider_updated_at),
                "first_synced_at": _ensure_utc(bar.first_synced_at),
                "last_synced_at": _ensure_utc(bar.last_synced_at),
            }
            for bar in bars
        ]
        stmt = insert(MarketBar1dModel).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_market_bars_1d_ticker_adjustment_trading_day",
            set_={
                "bucket_start_at_utc": stmt.excluded.bucket_start_at_utc,
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "vw": stmt.excluded.vw,
                "trade_count": stmt.excluded.trade_count,
                "provider_updated_at": stmt.excluded.provider_updated_at,
                "last_synced_at": stmt.excluded.last_synced_at,
            },
        )
        await self._session.execute(stmt)

    async def delete_1m_before(
        self,
        *,
        threshold_day: date,
    ) -> int:
        stmt = delete(MarketBar1mModel).where(MarketBar1mModel.trading_day < threshold_day)
        result = cast(CursorResult[object], await self._session.execute(stmt))
        return int(result.rowcount if result.rowcount is not None else 0)

    async def delete_1m_by_session_kinds(self, *, session_kinds: list[str]) -> int:
        stmt = delete(MarketBar1mModel).where(MarketBar1mModel.session_kind.in_(session_kinds))
        result = cast(CursorResult[object], await self._session.execute(stmt))
        return int(result.rowcount if result.rowcount is not None else 0)

    async def delete_1d_before(self, *, threshold_day: date) -> int:
        stmt = delete(MarketBar1dModel).where(MarketBar1dModel.trading_day < threshold_day)
        result = cast(CursorResult[object], await self._session.execute(stmt))
        return int(result.rowcount if result.rowcount is not None else 0)
