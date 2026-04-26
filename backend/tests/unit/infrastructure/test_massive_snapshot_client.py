"""Massive snapshot client tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from domain.entities import MarketDataMode
from infrastructure.external.massive_snapshot_client import MassiveSnapshotClient


def test_massive_snapshot_client_maps_complete_snapshot_payload() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "count": 1,
                "tickers": [
                    {
                        "ticker": "aapl",
                        "todaysChange": 1.23,
                        "todaysChangePerc": 0.58,
                        "updated": 1775658600000,
                        "day": {
                            "o": 211.10,
                            "h": 213.00,
                            "l": 210.60,
                            "c": 212.00,
                            "v": 45678901,
                        },
                        "min": {
                            "c": 212.34,
                            "t": 1775658600000,
                        },
                        "lastTrade": {
                            "p": 212.34,
                            "t": 1775658600000,
                        },
                        "prevDay": {
                            "c": 211.11,
                        },
                    }
                ],
            },
        )

    transport = httpx.MockTransport(
        handler
    )
    client = MassiveSnapshotClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=transport, base_url="https://api.massive.com"),
    )

    result = asyncio.run(
        client.fetch_snapshots(
            tickers=["AAPL"],
            mode=MarketDataMode(delay_minutes=15),
            data_source="massive_fallback",
        )
    )

    assert len(captured_requests) == 1
    assert captured_requests[0].url.path == "/v2/snapshot/locale/us/markets/stocks/tickers"
    assert dict(captured_requests[0].url.params) == {"tickers": "AAPL"}
    assert result.unresolved_tickers == []
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.ticker == "AAPL"
    assert snapshot.last == 212.34
    assert snapshot.regular_close == 212.00
    assert snapshot.change == 1.23
    assert snapshot.change_pct == 0.58
    assert snapshot.market_status == "closed"
    assert snapshot.session == "unknown"
    assert snapshot.trading_day is None
    assert snapshot.delay_minutes == 15
    assert snapshot.is_realtime is False
    assert snapshot.provider_updated_at == datetime(2026, 4, 8, 14, 30, tzinfo=UTC)
    assert snapshot.last_trade_at == datetime(2026, 4, 8, 14, 30, tzinfo=UTC)


def test_massive_snapshot_client_marks_missing_change_as_unresolved() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "tickers": [
                    {
                        "ticker": "NVDA",
                        "todaysChangePerc": 0.42,
                        "updated": 1775658600000,
                        "day": {
                            "o": 101.0,
                            "h": 103.0,
                            "l": 100.5,
                            "c": 102.0,
                            "v": 1200,
                        },
                        "prevDay": {
                            "c": 100.0,
                        },
                    }
                ]
            },
        )
    )
    client = MassiveSnapshotClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=transport, base_url="https://api.massive.com"),
    )

    result = asyncio.run(
        client.fetch_snapshots(
            tickers=["NVDA"],
            mode=MarketDataMode(delay_minutes=15),
            data_source="massive_fallback",
        )
    )

    assert result.snapshots == []
    assert result.unresolved_tickers == ["NVDA"]


def test_massive_snapshot_client_marks_missing_change_pct_as_unresolved() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "tickers": [
                    {
                        "ticker": "MSFT",
                        "todaysChange": 0.75,
                        "updated": 1775658600000,
                        "day": {
                            "o": 312.0,
                            "h": 315.0,
                            "l": 311.0,
                            "c": 314.0,
                            "v": 4500,
                        },
                        "prevDay": {
                            "c": 313.25,
                        },
                    }
                ]
            },
        )
    )
    client = MassiveSnapshotClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=transport, base_url="https://api.massive.com"),
    )

    result = asyncio.run(
        client.fetch_snapshots(
            tickers=["MSFT"],
            mode=MarketDataMode(delay_minutes=15),
            data_source="massive_fallback",
        )
    )

    assert result.snapshots == []
    assert result.unresolved_tickers == ["MSFT"]
