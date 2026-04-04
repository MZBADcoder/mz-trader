"""Get watchlist use case."""

from __future__ import annotations

from domain.entities import WatchlistItem
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory


class GetWatchlistService:
    """Return the current user's watchlist."""

    def __init__(self, *, uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: str) -> list[WatchlistItem]:
        async with self._uow_factory.build() as uow:
            return await uow.watchlist.list_by_user(user_id)
