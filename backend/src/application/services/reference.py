"""Ticker reference search use case."""

from __future__ import annotations

from domain.entities import TickerSearchResult
from infrastructure.external.massive_reference_client import MassiveReferenceClient


class SearchReferenceTickersService:
    """Search Massive stock reference data for ticker suggestions."""

    def __init__(self, *, reference_client: MassiveReferenceClient) -> None:
        self._reference_client = reference_client

    async def execute(self, *, query: str, limit: int) -> list[TickerSearchResult]:
        return await self._reference_client.search_tickers(query=query.strip(), limit=min(limit, 20))
