"""Massive reference client tests."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from domain.exceptions import InternalError
from infrastructure.external.massive_reference_client import MassiveReferenceClient


def test_massive_reference_client_maps_search_results() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "results": [
                    {
                        "ticker": "aapl",
                        "name": "Apple Inc.",
                        "primary_exchange": "XNAS",
                        "type": "CS",
                        "active": True,
                        "ignored": "field",
                    }
                ]
            },
        )
    )
    client = MassiveReferenceClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=transport, base_url="https://api.massive.com"),
    )

    results = asyncio.run(client.search_tickers(query="apple", limit=10))

    assert len(results) == 1
    assert results[0].ticker == "AAPL"
    assert results[0].name == "Apple Inc."


def test_massive_reference_client_normalizes_upstream_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"status": "error"}))
    client = MassiveReferenceClient(
        api_key="key",
        base_url="https://api.massive.com",
        client=httpx.AsyncClient(transport=transport, base_url="https://api.massive.com"),
    )

    with pytest.raises(InternalError):
        asyncio.run(client.ticker_exists("AAPL"))
