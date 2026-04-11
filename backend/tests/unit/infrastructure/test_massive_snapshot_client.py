"""Massive snapshot client tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from domain.entities import MarketDataMode
from infrastructure.external.massive_snapshot_client import MassiveSnapshotClient


def test_massive_snapshot_client_maps_complete_snapshot_payload() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "tickers": [
                    {
                        "ticker": "aapl",
                        "todaysChange": 1.23,
                        "todaysChangePerc": 0.58,
                        "updated": "2026-04-08T08:30:00Z",
                        "session": {
                            "open": 211.10,
                            "high": 213.00,
                            "low": 210.60,
                            "close": 212.34,
                            "volume": 45678901,
                            "marketStatus": "regular",
                        },
                        "prevDay": {
                            "close": 211.11,
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
            tickers=["AAPL"],
            mode=MarketDataMode(delay_minutes=15),
            data_source="massive_fallback",
        )
    )

    assert result.unresolved_tickers == []
    assert len(result.snapshots) == 1
    snapshot = result.snapshots[0]
    assert snapshot.ticker == "AAPL"
    assert snapshot.last == 212.34
    assert snapshot.change == 1.23
    assert snapshot.change_pct == 0.58
    assert snapshot.market_status == "regular"
    assert snapshot.delay_minutes == 15
    assert snapshot.is_realtime is False
    assert snapshot.provider_updated_at == datetime(2026, 4, 8, 8, 30, tzinfo=UTC)


def test_massive_snapshot_client_marks_missing_change_as_unresolved() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "tickers": [
                    {
                        "ticker": "NVDA",
                        "todaysChangePerc": 0.42,
                        "updated": "2026-04-08T08:30:00Z",
                        "session": {
                            "open": 101.0,
                            "high": 103.0,
                            "low": 100.5,
                            "close": 102.0,
                            "volume": 1200,
                            "marketStatus": "regular",
                        },
                        "prevDay": {
                            "close": 100.0,
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
                        "updated": "2026-04-08T08:30:00Z",
                        "session": {
                            "open": 312.0,
                            "high": 315.0,
                            "low": 311.0,
                            "close": 314.0,
                            "volume": 4500,
                            "marketStatus": "regular",
                        },
                        "prevDay": {
                            "close": 313.25,
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
