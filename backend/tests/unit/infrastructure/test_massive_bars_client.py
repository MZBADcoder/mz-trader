"""Massive bars client tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from infrastructure.external.massive_bars_client import MassiveBarsClient


def test_massive_bars_client_maps_official_custom_bars_payload() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "ticker": "AAPL",
                "adjusted": True,
                "queryCount": 2,
                "resultsCount": 2,
                "status": "OK",
                "results": [
                    {
                        "o": 100.0,
                        "h": 101.5,
                        "l": 99.5,
                        "c": 101.0,
                        "v": 1000,
                        "vw": 100.8,
                        "n": 42,
                        "t": 1776260100000,
                        "otc": False,
                    },
                    {
                        "o": 101,
                        "h": 102,
                        "l": 100.5,
                        "c": 101.8,
                        "v": 1200.0,
                        "t": 1776260160000,
                    },
                ],
            },
        )

    client = MassiveBarsClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.massive.com"),
    )

    bars = asyncio.run(
        client.fetch_range(
            ticker="AAPL",
            multiplier=1,
            timespan="minute",
            from_value="1776260100000",
            to_value="1776260220000",
            adjusted=True,
        )
    )

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.path == "/v2/aggs/ticker/AAPL/range/1/minute/1776260100000/1776260220000"
    assert dict(request.url.params) == {
        "adjusted": "true",
        "sort": "asc",
        "limit": "50000",
    }
    assert len(bars) == 2
    assert bars[0].time == datetime(2026, 4, 15, 13, 35, tzinfo=UTC)
    assert bars[0].open == 100.0
    assert bars[0].high == 101.5
    assert bars[0].low == 99.5
    assert bars[0].close == 101.0
    assert bars[0].volume == 1000
    assert bars[0].vw == 100.8
    assert bars[0].trade_count == 42
    assert bars[0].provider_updated_at == datetime(2026, 4, 15, 13, 35, tzinfo=UTC)
    assert bars[1].vw is None
    assert bars[1].trade_count == 0


def test_massive_bars_client_skips_results_missing_required_ohlcv_fields() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "results": [
                    {
                        "o": 100.0,
                        "h": 101.5,
                        "l": 99.5,
                        "v": 1000,
                        "t": 1776260100000,
                    },
                    {
                        "o": 101.0,
                        "h": 102.0,
                        "l": 100.0,
                        "c": 101.5,
                        "v": 1200,
                        "t": 1776260160000,
                    },
                ],
            },
        )
    )
    client = MassiveBarsClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=transport, base_url="https://api.massive.com"),
    )

    bars = asyncio.run(
        client.fetch_range(
            ticker="AAPL",
            multiplier=1,
            timespan="minute",
            from_value="1776260100000",
            to_value="1776260220000",
            adjusted=True,
        )
    )

    assert len(bars) == 1
    assert bars[0].close == 101.5
