"""Massive snapshot client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from domain.entities import MarketDataMode, Snapshot
from domain.exceptions import MarketSnapshotUpstreamUnavailableError


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MassiveSnapshotBatchResponse:
    """Normalized result from one Massive snapshot batch request."""

    snapshots: list[Snapshot]
    unresolved_tickers: list[str]


class MassiveSnapshotClient:
    """Thin async client for Massive stock snapshot endpoints."""

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

    async def fetch_snapshots(
        self,
        *,
        tickers: list[str],
        mode: MarketDataMode,
        data_source: str,
    ) -> MassiveSnapshotBatchResponse:
        """Fetch and normalize a batch snapshot response."""
        if not tickers:
            return MassiveSnapshotBatchResponse(snapshots=[], unresolved_tickers=[])

        payload = await self._request(tickers=tickers)
        raw_items = payload.get("tickers", [])
        if not isinstance(raw_items, list):
            raise MarketSnapshotUpstreamUnavailableError(detail="Snapshot provider payload is invalid.")

        snapshots_by_ticker: dict[str, Snapshot] = {}
        unresolved_tickers: list[str] = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue
            snapshot = self._map_snapshot(item=item, mode=mode, data_source=data_source)
            if snapshot is None:
                ticker = str(item.get("ticker", "")).upper()
                if ticker:
                    unresolved_tickers.append(ticker)
                continue
            snapshots_by_ticker[snapshot.ticker] = snapshot

        requested = set(tickers)
        resolved = set(snapshots_by_ticker)
        missing = sorted(requested - resolved)
        for ticker in missing:
            if ticker not in unresolved_tickers:
                unresolved_tickers.append(ticker)

        return MassiveSnapshotBatchResponse(
            snapshots=[snapshots_by_ticker[ticker] for ticker in tickers if ticker in snapshots_by_ticker],
            unresolved_tickers=unresolved_tickers,
        )

    async def _request(self, *, tickers: list[str]) -> dict[str, Any]:
        try:
            response = await self._client.get(
                "/v2/snapshot/locale/us/markets/stocks/tickers",
                params={"tickers": ",".join(tickers)},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.exception(
                "massive snapshot request failed",
                extra={"upstream_service": "massive", "ticker_count": len(tickers)},
            )
            raise MarketSnapshotUpstreamUnavailableError(
                detail="Snapshot provider request failed."
            ) from exc

        if not isinstance(payload, dict):
            raise MarketSnapshotUpstreamUnavailableError(detail="Snapshot provider payload is invalid.")
        return payload

    def _map_snapshot(
        self,
        *,
        item: dict[str, Any],
        mode: MarketDataMode,
        data_source: str,
    ) -> Snapshot | None:
        ticker = str(item.get("ticker", "")).upper()
        if not ticker:
            return None

        session = self._read_dict(item, "session", "day")
        prev_day = self._read_dict(item, "prevDay", "prev_day")
        last_trade = self._read_dict(item, "lastTrade", "last_trade")

        last = (
            self._read_float(last_trade, "p", "price")
            or self._read_float(item, "last")
            or self._read_float(session, "close", "c")
        )
        open_price = self._read_float(session, "open", "o")
        high = self._read_float(session, "high", "h")
        low = self._read_float(session, "low", "l")
        volume = self._read_int(session, "volume", "v")
        prev_close = (
            self._read_float(prev_day, "close", "c")
            or self._read_float(item, "prevClose", "prev_close")
        )

        change = self._read_float(item, "todaysChange", "change")

        change_pct = self._read_float(item, "todaysChangePerc", "todaysChangePercent", "change_pct")

        provider_updated_at = self._read_timestamp(
            item,
            "updated",
            "updated_at",
            fallback_sources=(last_trade, session, prev_day),
        )
        market_status = (
            self._read_str(item, "market_status", "marketStatus")
            or self._read_str(session, "market_status", "marketStatus")
            or "closed"
        )

        if None in (last, change, change_pct, open_price, high, low, volume, prev_close, provider_updated_at):
            return None

        return Snapshot(
            ticker=ticker,
            last=last,
            change=change,
            change_pct=change_pct,
            open=open_price,
            high=high,
            low=low,
            volume=volume,
            prev_close=prev_close,
            market_status=market_status,
            delay_minutes=mode.delay_minutes,
            is_realtime=mode.is_realtime,
            provider_updated_at=provider_updated_at,
            fetched_at=datetime.now(UTC),
            data_source=data_source,
        )

    def _read_dict(self, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return {}

    def _read_float(self, payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            if key not in payload:
                continue
            value = payload[key]
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _read_int(self, payload: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            if key not in payload:
                continue
            value = payload[key]
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _read_str(self, payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _read_timestamp(
        self,
        payload: dict[str, Any],
        *keys: str,
        fallback_sources: tuple[dict[str, Any], ...] = (),
    ) -> datetime | None:
        for key in keys:
            if key in payload:
                parsed = self._parse_timestamp(payload[key])
                if parsed is not None:
                    return parsed

        for source in fallback_sources:
            for key in ("updated", "updated_at", "t", "timestamp"):
                if key not in source:
                    continue
                parsed = self._parse_timestamp(source[key])
                if parsed is not None:
                    return parsed
        return None

    def _parse_timestamp(self, value: object) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)

        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None

        absolute_value = abs(numeric_value)
        if absolute_value >= 1_000_000_000_000_000_000:
            seconds = numeric_value / 1_000_000_000
        elif absolute_value >= 1_000_000_000_000_000:
            seconds = numeric_value / 1_000_000
        elif absolute_value >= 1_000_000_000_000:
            seconds = numeric_value / 1_000
        else:
            seconds = numeric_value
        return datetime.fromtimestamp(seconds, tz=UTC)
