"""Watchlist service tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from application.services.watchlist import (
    AddWatchlistItemService,
    DeleteWatchlistItemService,
    GetWatchlistService,
    UpdateWatchlistService,
)
from domain.entities import WatchlistItem
from domain.exceptions import (
    WatchlistLimitExceededError,
    WatchlistOrderInvalidError,
    WatchlistTickerDuplicateError,
    WatchlistTickerNotFoundError,
    WatchlistTickerNotSupportedError,
)


def _watchlist_item(
    ticker: str, *, created_at: datetime, position: int = 0
) -> WatchlistItem:
    return WatchlistItem(
        id=f"id-{ticker}",
        user_id="user-1",
        ticker=ticker,
        position=position,
        created_at=created_at,
    )


class FakeUserRepository:
    async def get_by_email(self, email: str):
        return None


class FakeWatchlistRepository:
    def __init__(self, items: list[WatchlistItem] | None = None) -> None:
        self.items = items or []
        self.locked_user_ids: list[str] = []

    async def list_by_user(self, user_id: str) -> list[WatchlistItem]:
        return list(self.items)

    async def exists(self, *, user_id: str, ticker: str) -> bool:
        return any(item.ticker == ticker for item in self.items)

    async def count_by_user(self, user_id: str) -> int:
        return len(self.items)

    async def lock_owner(self, user_id: str) -> None:
        self.locked_user_ids.append(user_id)

    async def add(self, *, user_id: str, ticker: str) -> WatchlistItem:
        item = _watchlist_item(
            ticker, created_at=datetime.now(UTC), position=len(self.items)
        )
        self.items.append(item)
        return item

    async def reorder(
        self, *, user_id: str, ordered_tickers: list[str]
    ) -> list[WatchlistItem]:
        by_ticker = {item.ticker: item for item in self.items}
        self.items = [
            WatchlistItem(
                id=by_ticker[ticker].id,
                user_id=by_ticker[ticker].user_id,
                ticker=ticker,
                position=position,
                created_at=by_ticker[ticker].created_at,
            )
            for position, ticker in enumerate(ordered_tickers)
        ]
        return list(self.items)

    async def delete(self, *, user_id: str, ticker: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.ticker != ticker]
        return len(self.items) != before


class FakeTickerBarsStateRepository:
    def __init__(self) -> None:
        self.pending_tickers: list[str] = []

    async def ensure_pending(self, *, ticker: str, requested_at: datetime) -> None:
        self.pending_tickers.append(ticker)


class FakeUow:
    def __init__(self, watchlist: FakeWatchlistRepository) -> None:
        self.users = FakeUserRepository()
        self.watchlist = watchlist
        self.ticker_bars_state = FakeTickerBarsStateRepository()
        self.committed = False

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeUowFactory:
    def __init__(self, uow: FakeUow) -> None:
        self._uow = uow

    def build(self) -> FakeUow:
        return self._uow


class FakeReferenceClient:
    def __init__(self, *, supported_tickers: set[str]) -> None:
        self.supported_tickers = supported_tickers

    async def ticker_exists(self, ticker: str) -> bool:
        return ticker in self.supported_tickers


def test_get_watchlist_service_returns_items_in_existing_order() -> None:
    base_time = datetime.now(UTC)
    items = [
        _watchlist_item("AAPL", created_at=base_time),
        _watchlist_item("NVDA", created_at=base_time + timedelta(minutes=1)),
    ]
    service = GetWatchlistService(
        uow_factory=FakeUowFactory(FakeUow(FakeWatchlistRepository(items)))
    )

    result = asyncio.run(service.execute(user_id="user-1"))

    assert [item.ticker for item in result] == ["AAPL", "NVDA"]


def test_add_watchlist_item_service_uppercases_and_commits() -> None:
    watchlist = FakeWatchlistRepository()
    uow = FakeUow(watchlist)
    service = AddWatchlistItemService(
        uow_factory=FakeUowFactory(uow),
        reference_client=FakeReferenceClient(supported_tickers={"AAPL"}),
    )

    item = asyncio.run(service.execute(user_id="user-1", ticker="aapl"))

    assert item.ticker == "AAPL"
    assert uow.committed is True
    assert watchlist.locked_user_ids == ["user-1"]
    assert uow.ticker_bars_state.pending_tickers == ["AAPL"]


def test_add_watchlist_item_service_rejects_duplicate() -> None:
    watchlist = FakeWatchlistRepository(
        [_watchlist_item("AAPL", created_at=datetime.now(UTC))]
    )
    service = AddWatchlistItemService(
        uow_factory=FakeUowFactory(FakeUow(watchlist)),
        reference_client=FakeReferenceClient(supported_tickers={"AAPL"}),
    )

    with pytest.raises(WatchlistTickerDuplicateError):
        asyncio.run(service.execute(user_id="user-1", ticker="AAPL"))


def test_add_watchlist_item_service_rejects_limit_exceeded() -> None:
    base_time = datetime.now(UTC)
    items = [
        _watchlist_item(f"T{i}", created_at=base_time + timedelta(seconds=i))
        for i in range(50)
    ]
    service = AddWatchlistItemService(
        uow_factory=FakeUowFactory(FakeUow(FakeWatchlistRepository(items))),
        reference_client=FakeReferenceClient(supported_tickers={"MSFT"}),
    )

    with pytest.raises(WatchlistLimitExceededError):
        asyncio.run(service.execute(user_id="user-1", ticker="MSFT"))


def test_add_watchlist_item_service_rejects_unsupported_ticker() -> None:
    service = AddWatchlistItemService(
        uow_factory=FakeUowFactory(FakeUow(FakeWatchlistRepository())),
        reference_client=FakeReferenceClient(supported_tickers=set()),
    )

    with pytest.raises(WatchlistTickerNotSupportedError):
        asyncio.run(service.execute(user_id="user-1", ticker="MSFT"))


def test_delete_watchlist_item_service_rejects_missing_ticker() -> None:
    service = DeleteWatchlistItemService(
        uow_factory=FakeUowFactory(FakeUow(FakeWatchlistRepository()))
    )

    with pytest.raises(WatchlistTickerNotFoundError):
        asyncio.run(service.execute(user_id="user-1", ticker="AAPL"))


def test_update_watchlist_service_reorders_existing_tickers_and_commits() -> None:
    base_time = datetime.now(UTC)
    watchlist = FakeWatchlistRepository(
        [
            _watchlist_item("AAPL", created_at=base_time, position=0),
            _watchlist_item(
                "NVDA", created_at=base_time + timedelta(minutes=1), position=1
            ),
            _watchlist_item(
                "MSFT", created_at=base_time + timedelta(minutes=2), position=2
            ),
        ]
    )
    uow = FakeUow(watchlist)
    service = UpdateWatchlistService(uow_factory=FakeUowFactory(uow))

    result = asyncio.run(
        service.execute(user_id="user-1", tickers=["msft", "aapl", "nvda"])
    )

    assert [item.ticker for item in result] == ["MSFT", "AAPL", "NVDA"]
    assert [item.position for item in result] == [0, 1, 2]
    assert watchlist.locked_user_ids == ["user-1"]
    assert uow.committed is True


def test_update_watchlist_service_rejects_duplicate_tickers() -> None:
    base_time = datetime.now(UTC)
    service = UpdateWatchlistService(
        uow_factory=FakeUowFactory(
            FakeUow(
                FakeWatchlistRepository(
                    [
                        _watchlist_item("AAPL", created_at=base_time, position=0),
                        _watchlist_item(
                            "NVDA",
                            created_at=base_time + timedelta(minutes=1),
                            position=1,
                        ),
                    ]
                )
            )
        )
    )

    with pytest.raises(WatchlistOrderInvalidError):
        asyncio.run(service.execute(user_id="user-1", tickers=["AAPL", "AAPL"]))


def test_update_watchlist_service_rejects_missing_existing_ticker() -> None:
    base_time = datetime.now(UTC)
    service = UpdateWatchlistService(
        uow_factory=FakeUowFactory(
            FakeUow(
                FakeWatchlistRepository(
                    [
                        _watchlist_item("AAPL", created_at=base_time, position=0),
                        _watchlist_item(
                            "NVDA",
                            created_at=base_time + timedelta(minutes=1),
                            position=1,
                        ),
                    ]
                )
            )
        )
    )

    with pytest.raises(WatchlistOrderInvalidError):
        asyncio.run(service.execute(user_id="user-1", tickers=["AAPL"]))


def test_update_watchlist_service_rejects_unknown_ticker() -> None:
    service = UpdateWatchlistService(
        uow_factory=FakeUowFactory(
            FakeUow(
                FakeWatchlistRepository(
                    [_watchlist_item("AAPL", created_at=datetime.now(UTC), position=0)]
                )
            )
        )
    )

    with pytest.raises(WatchlistOrderInvalidError):
        asyncio.run(service.execute(user_id="user-1", tickers=["AAPL", "MSFT"]))


def test_update_watchlist_service_allows_empty_watchlist_order() -> None:
    uow = FakeUow(FakeWatchlistRepository())
    service = UpdateWatchlistService(uow_factory=FakeUowFactory(uow))

    result = asyncio.run(service.execute(user_id="user-1", tickers=[]))

    assert result == []
    assert uow.committed is True
