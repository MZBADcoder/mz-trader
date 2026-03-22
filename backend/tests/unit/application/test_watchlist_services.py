"""Watchlist service tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from application.services.watchlist import AddWatchlistItemService, DeleteWatchlistItemService, GetWatchlistService
from domain.entities import WatchlistItem
from domain.exceptions import (
    WatchlistLimitExceededError,
    WatchlistTickerDuplicateError,
    WatchlistTickerNotFoundError,
    WatchlistTickerNotSupportedError,
)


def _watchlist_item(ticker: str, *, created_at: datetime) -> WatchlistItem:
    return WatchlistItem(
        id=f"id-{ticker}",
        user_id="user-1",
        ticker=ticker,
        created_at=created_at,
    )


class FakeUserRepository:
    async def get_by_email(self, email: str):
        return None


class FakeWatchlistRepository:
    def __init__(self, items: list[WatchlistItem] | None = None) -> None:
        self.items = items or []

    async def list_by_user(self, user_id: str) -> list[WatchlistItem]:
        return list(self.items)

    async def exists(self, *, user_id: str, ticker: str) -> bool:
        return any(item.ticker == ticker for item in self.items)

    async def count_by_user(self, user_id: str) -> int:
        return len(self.items)

    async def add(self, *, user_id: str, ticker: str) -> WatchlistItem:
        item = _watchlist_item(ticker, created_at=datetime.now(UTC))
        self.items.append(item)
        return item

    async def delete(self, *, user_id: str, ticker: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.ticker != ticker]
        return len(self.items) != before


class FakeUow:
    def __init__(self, watchlist: FakeWatchlistRepository) -> None:
        self.users = FakeUserRepository()
        self.watchlist = watchlist
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
    service = GetWatchlistService(uow_factory=FakeUowFactory(FakeUow(FakeWatchlistRepository(items))))

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


def test_add_watchlist_item_service_rejects_duplicate() -> None:
    watchlist = FakeWatchlistRepository([_watchlist_item("AAPL", created_at=datetime.now(UTC))])
    service = AddWatchlistItemService(
        uow_factory=FakeUowFactory(FakeUow(watchlist)),
        reference_client=FakeReferenceClient(supported_tickers={"AAPL"}),
    )

    with pytest.raises(WatchlistTickerDuplicateError):
        asyncio.run(service.execute(user_id="user-1", ticker="AAPL"))


def test_add_watchlist_item_service_rejects_limit_exceeded() -> None:
    base_time = datetime.now(UTC)
    items = [_watchlist_item(f"T{i}", created_at=base_time + timedelta(seconds=i)) for i in range(50)]
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
    service = DeleteWatchlistItemService(uow_factory=FakeUowFactory(FakeUow(FakeWatchlistRepository())))

    with pytest.raises(WatchlistTickerNotFoundError):
        asyncio.run(service.execute(user_id="user-1", ticker="AAPL"))
