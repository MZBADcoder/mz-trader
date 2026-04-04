"""Delete watchlist item use case."""

from __future__ import annotations

from domain.exceptions import WatchlistTickerNotFoundError
from domain.rules import validate_ticker
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory


class DeleteWatchlistItemService:
    """Delete a ticker from the current user's watchlist."""

    def __init__(self, *, uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: str, ticker: str) -> None:
        normalized_ticker = validate_ticker(ticker)

        async with self._uow_factory.build() as uow:
            deleted = await uow.watchlist.delete(user_id=user_id, ticker=normalized_ticker)
            if not deleted:
                raise WatchlistTickerNotFoundError()
            await uow.commit()
