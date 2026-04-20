"""Massive bars client."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from domain.entities import ProviderBar
from domain.exceptions import MarketBarsUpstreamUnavailableError


logger = logging.getLogger(__name__)


class MassiveBarsClient:
    """Thin async client for Massive aggregate bar endpoints."""

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
        if self._owns_client:
            await self._client.aclose()

    async def fetch_range(
        self,
        *,
        ticker: str,
        multiplier: int,
        timespan: str,
        from_value: str,
        to_value: str,
        adjusted: bool,
        sort: str = "asc",
        limit: int = 50_000,
    ) -> list[ProviderBar]:
        try:
            response = await self._client.get(
                f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_value}/{to_value}",
                params={
                    "adjusted": "true" if adjusted else "false",
                    "sort": sort,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.exception(
                "massive bars request failed",
                extra={
                    "upstream_service": "massive",
                    "ticker": ticker,
                    "multiplier": multiplier,
                    "timespan": timespan,
                    "from_value": from_value,
                    "to_value": to_value,
                },
            )
            raise MarketBarsUpstreamUnavailableError(detail="Bars provider request failed.") from exc

        if not isinstance(payload, dict):
            raise MarketBarsUpstreamUnavailableError(detail="Bars provider payload is invalid.")

        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            raise MarketBarsUpstreamUnavailableError(detail="Bars provider payload is invalid.")

        bars: list[ProviderBar] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            mapped = self._map_bar(item)
            if mapped is not None:
                bars.append(mapped)
        return bars

    def _map_bar(self, item: dict[str, Any]) -> ProviderBar | None:
        timestamp = item.get("t")
        open_price = item.get("o")
        high = item.get("h")
        low = item.get("l")
        close = item.get("c")
        volume = item.get("v")

        if not isinstance(timestamp, int):
            return None
        if not all(isinstance(value, (int, float)) for value in (open_price, high, low, close, volume)):
            return None
        assert isinstance(open_price, (int, float))
        assert isinstance(high, (int, float))
        assert isinstance(low, (int, float))
        assert isinstance(close, (int, float))
        assert isinstance(volume, (int, float))

        return ProviderBar(
            time=datetime.fromtimestamp(timestamp / 1000, tz=UTC),
            open=float(open_price),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=int(volume),
            vw=float(item["vw"]) if isinstance(item.get("vw"), (int, float)) else None,
            trade_count=int(item["n"]) if isinstance(item.get("n"), int) else 0,
            provider_updated_at=datetime.fromtimestamp(timestamp / 1000, tz=UTC),
        )
