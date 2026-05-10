"""Watchlist repository implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import WatchlistItem
from domain.exceptions import WatchlistTickerDuplicateError
from infrastructure.db.mappers import to_watchlist_item_entity
from infrastructure.db.models import UserModel, WatchlistItemModel


class WatchlistRepository:
    """Persist and query watchlist items."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: str) -> list[WatchlistItem]:
        """Return a user's watchlist ordered by persisted position."""
        stmt = (
            select(WatchlistItemModel)
            .where(WatchlistItemModel.user_id == uuid.UUID(user_id))
            .order_by(
                WatchlistItemModel.sort_order.asc(),
                WatchlistItemModel.created_at.asc(),
                WatchlistItemModel.id.asc(),
            )
        )
        result = await self._session.scalars(stmt)
        return [to_watchlist_item_entity(model) for model in result.all()]

    async def exists(self, *, user_id: str, ticker: str) -> bool:
        """Check whether a ticker already exists for the user."""
        stmt = (
            select(WatchlistItemModel.id)
            .where(
                WatchlistItemModel.user_id == uuid.UUID(user_id),
                WatchlistItemModel.ticker == ticker,
            )
            .limit(1)
        )
        return await self._session.scalar(stmt) is not None

    async def count_by_user(self, user_id: str) -> int:
        """Return the number of watchlist items a user has."""
        stmt = (
            select(func.count())
            .select_from(WatchlistItemModel)
            .where(WatchlistItemModel.user_id == uuid.UUID(user_id))
        )
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def list_distinct_tickers(self) -> list[str]:
        """Return all distinct watchlist tickers across users."""
        stmt = (
            select(WatchlistItemModel.ticker)
            .distinct()
            .order_by(WatchlistItemModel.ticker.asc())
        )
        result = await self._session.scalars(stmt)
        return [ticker for ticker in result.all() if isinstance(ticker, str)]

    async def lock_owner(self, user_id: str) -> None:
        """Serialize watchlist mutations per user."""
        stmt = (
            select(UserModel.id)
            .where(UserModel.id == uuid.UUID(user_id))
            .with_for_update()
        )
        await self._session.execute(stmt)

    async def add(self, *, user_id: str, ticker: str) -> WatchlistItem:
        """Create a watchlist item."""
        user_uuid = uuid.UUID(user_id)
        next_sort_order = await self._next_sort_order(user_uuid)
        now = datetime.now(UTC)
        model = WatchlistItemModel(
            id=uuid.uuid4(),
            user_id=user_uuid,
            ticker=ticker,
            sort_order=next_sort_order,
            created_at=now,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise WatchlistTickerDuplicateError() from exc
        await self._session.refresh(model)
        return to_watchlist_item_entity(model)

    async def reorder(
        self, *, user_id: str, ordered_tickers: list[str]
    ) -> list[WatchlistItem]:
        """Persist a complete ordered ticker list for one user."""
        user_uuid = uuid.UUID(user_id)
        for position, ticker in enumerate(ordered_tickers):
            stmt = (
                update(WatchlistItemModel)
                .where(
                    WatchlistItemModel.user_id == user_uuid,
                    WatchlistItemModel.ticker == ticker,
                )
                .values(sort_order=position)
            )
            await self._session.execute(stmt)
        await self._session.flush()
        return await self.list_by_user(user_id)

    async def delete(self, *, user_id: str, ticker: str) -> bool:
        """Delete a watchlist item if it exists."""
        user_uuid = uuid.UUID(user_id)
        stmt = delete(WatchlistItemModel).where(
            WatchlistItemModel.user_id == user_uuid,
            WatchlistItemModel.ticker == ticker,
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        deleted = (result.rowcount or 0) > 0
        if deleted:
            await self._compact_sort_order(user_uuid)
        return deleted

    async def _next_sort_order(self, user_id: uuid.UUID) -> int:
        stmt = select(func.max(WatchlistItemModel.sort_order)).where(
            WatchlistItemModel.user_id == user_id
        )
        max_sort_order = await self._session.scalar(stmt)
        if max_sort_order is None:
            return 0
        return int(max_sort_order) + 1

    async def _compact_sort_order(self, user_id: uuid.UUID) -> None:
        stmt = (
            select(WatchlistItemModel.id)
            .where(WatchlistItemModel.user_id == user_id)
            .order_by(
                WatchlistItemModel.sort_order.asc(),
                WatchlistItemModel.created_at.asc(),
                WatchlistItemModel.id.asc(),
            )
        )
        result = await self._session.scalars(stmt)
        for position, item_id in enumerate(result.all()):
            await self._session.execute(
                update(WatchlistItemModel)
                .where(WatchlistItemModel.id == item_id)
                .values(sort_order=position)
            )
        await self._session.flush()
