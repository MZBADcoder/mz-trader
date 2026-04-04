"""Ticker search service tests."""

from __future__ import annotations

import asyncio

import pytest

from application.services.ticker_search import SearchTickersService
from domain.exceptions import ValidationError


class FakeReferenceClient:
    async def search_tickers(self, *, query: str, limit: int):
        return [{"query": query, "limit": limit}]


def test_search_tickers_service_rejects_blank_query() -> None:
    service = SearchTickersService(ticker_search_client=FakeReferenceClient())

    with pytest.raises(ValidationError):
        asyncio.run(service.execute(query="   ", limit=10))
