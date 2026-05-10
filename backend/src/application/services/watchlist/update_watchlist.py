"""Update watchlist order use case."""

from __future__ import annotations

from domain.entities import WatchlistItem
from domain.exceptions import WatchlistOrderInvalidError
from domain.rules import validate_watchlist_order_tickers
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory


class UpdateWatchlistService:
    """Persist a complete ticker order for the current user's watchlist."""

    def __init__(self, *, uow_factory: SqlAlchemyUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: str, tickers: list[str]) -> list[WatchlistItem]:
        normalized_tickers = validate_watchlist_order_tickers(tickers)

        async with self._uow_factory.build() as uow:
            await uow.watchlist.lock_owner(user_id)
            current_items = await uow.watchlist.list_by_user(user_id)
            current_tickers = [item.ticker for item in current_items]

            if set(normalized_tickers) != set(current_tickers) or len(
                normalized_tickers
            ) != len(current_tickers):
                raise WatchlistOrderInvalidError()

            items = await uow.watchlist.reorder(
                user_id=user_id, ordered_tickers=normalized_tickers
            )
            await uow.commit()
            return items
