"""Massive ticker reference client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from domain.entities import TickerSearchResult
from domain.exceptions import InternalError


logger = logging.getLogger(__name__)


class MassiveReferenceClient:
    """Thin async client for Massive stock reference endpoints."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def close(self) -> None:
        """Close the underlying client when owned by this instance."""
        if self._owns_client:
            await self._client.aclose()

    async def ticker_exists(self, ticker: str) -> bool:
        """Check whether a ticker exists in Massive stock reference data."""
        payload = await self._request(
            params={
                "ticker": ticker,
                "market": "stocks",
                "active": "true",
                "limit": 1,
            }
        )
        return bool(self._extract_results(payload))

    async def search_tickers(self, *, query: str, limit: int) -> list[TickerSearchResult]:
        """Search tickers and company names."""
        payload = await self._request(
            params={
                "search": query,
                "market": "stocks",
                "active": "true",
                "limit": limit,
            }
        )
        return [self._map_result(item) for item in self._extract_results(payload)]

    async def _request(self, *, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.get("/v3/reference/tickers", params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.exception("massive reference request failed", extra={"upstream_service": "massive"})
            raise InternalError(detail="Reference data provider request failed.") from exc

    def _extract_results(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise InternalError(detail="Reference data payload is invalid.")
        normalized: list[dict[str, Any]] = []
        for item in results:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized

    def _map_result(self, item: dict[str, Any]) -> TickerSearchResult:
        return TickerSearchResult(
            ticker=str(item.get("ticker", "")).upper(),
            name=str(item.get("name", "")),
            primary_exchange=str(item.get("primary_exchange", "")),
            type=str(item.get("type", "")),
            active=bool(item.get("active", False)),
        )
