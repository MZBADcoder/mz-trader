"""Search tickers use case."""

from __future__ import annotations

from domain.entities import TickerSearchResult
from domain.exceptions import ValidationError
from infrastructure.external.massive_reference_client import MassiveReferenceClient


class SearchTickersService:
    """Search Massive stock reference data for ticker suggestions."""

    def __init__(self, *, ticker_search_client: MassiveReferenceClient) -> None:
        self._ticker_search_client = ticker_search_client

    async def execute(self, *, query: str, limit: int) -> list[TickerSearchResult]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValidationError(detail="query: Search query must not be blank")
        return await self._ticker_search_client.search_tickers(query=normalized_query, limit=min(limit, 20))
