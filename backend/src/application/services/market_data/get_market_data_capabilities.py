"""Get market data capabilities use case."""

from __future__ import annotations

from domain.entities import MarketDataCapabilities, MarketDataMode


class GetMarketDataCapabilitiesService:
    """Return the resolved market-data capabilities."""

    def __init__(self, *, mode: MarketDataMode) -> None:
        self._mode = mode

    async def execute(self) -> MarketDataCapabilities:
        return MarketDataCapabilities(
            delay_minutes=self._mode.delay_minutes,
            is_realtime=self._mode.is_realtime,
            supports_stream=self._mode.supports_stream,
        )
