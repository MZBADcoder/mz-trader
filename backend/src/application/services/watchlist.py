"""Watchlist use cases."""

from __future__ import annotations

from domain.entities import WatchlistItem
from domain.exceptions import (
    WatchlistLimitExceededError,
    WatchlistTickerDuplicateError,
    WatchlistTickerNotFoundError,
    WatchlistTickerNotSupportedError,
)
from domain.rules import WATCHLIST_ITEM_LIMIT, validate_ticker
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external.massive_reference_client import MassiveReferenceClient


class GetWatchlistService:
    """Return the current user's watchlist."""

    def __init__(self, *, uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: str) -> list[WatchlistItem]:
        async with self._uow_factory.build() as uow:
            assert uow.watchlist is not None
            return await uow.watchlist.list_by_user(user_id)


class AddWatchlistItemService:
    """Validate and add a ticker to the current user's watchlist."""

    def __init__(
        self,
        *,
        uow_factory: SqlAlchemyUnitOfWorkFactory,
        reference_client: MassiveReferenceClient,
    ) -> None:
        self._uow_factory = uow_factory
        self._reference_client = reference_client

    async def execute(self, *, user_id: str, ticker: str) -> WatchlistItem:
        normalized_ticker = validate_ticker(ticker)

        async with self._uow_factory.build() as uow:
            assert uow.watchlist is not None
            if await uow.watchlist.exists(user_id=user_id, ticker=normalized_ticker):
                raise WatchlistTickerDuplicateError()

            item_count = await uow.watchlist.count_by_user(user_id)
            if item_count >= WATCHLIST_ITEM_LIMIT:
                raise WatchlistLimitExceededError()

            if not await self._reference_client.ticker_exists(normalized_ticker):
                raise WatchlistTickerNotSupportedError()

            item = await uow.watchlist.add(user_id=user_id, ticker=normalized_ticker)
            await uow.commit()
            return item


class DeleteWatchlistItemService:
    """Delete a ticker from the current user's watchlist."""

    def __init__(self, *, uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: str, ticker: str) -> None:
        normalized_ticker = validate_ticker(ticker)

        async with self._uow_factory.build() as uow:
            assert uow.watchlist is not None
            deleted = await uow.watchlist.delete(user_id=user_id, ticker=normalized_ticker)
            if not deleted:
                raise WatchlistTickerNotFoundError()
            await uow.commit()
