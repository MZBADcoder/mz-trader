"""Add watchlist item use case."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.entities import WatchlistItem
from domain.exceptions import (
    WatchlistLimitExceededError,
    WatchlistTickerDuplicateError,
    WatchlistTickerNotSupportedError,
)
from domain.rules import WATCHLIST_ITEM_LIMIT, validate_ticker
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external.massive_reference_client import MassiveReferenceClient


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
        if not await self._reference_client.ticker_exists(normalized_ticker):
            raise WatchlistTickerNotSupportedError()

        async with self._uow_factory.build() as uow:
            await uow.watchlist.lock_owner(user_id)

            if await uow.watchlist.exists(user_id=user_id, ticker=normalized_ticker):
                raise WatchlistTickerDuplicateError()

            item_count = await uow.watchlist.count_by_user(user_id)
            if item_count >= WATCHLIST_ITEM_LIMIT:
                raise WatchlistLimitExceededError()

            item = await uow.watchlist.add(user_id=user_id, ticker=normalized_ticker)
            await uow.ticker_bars_state.ensure_pending(
                ticker=normalized_ticker,
                requested_at=datetime.now(UTC),
            )
            await uow.commit()
            return item
