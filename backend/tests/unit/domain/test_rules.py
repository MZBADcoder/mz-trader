"""Domain rule tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from domain.exceptions import MarketBarsSessionUnsupportedError, WatchlistTickerInvalidError
from domain.rules import validate_bars_query, normalize_email, validate_ticker


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  USER@Example.COM ") == "user@example.com"


def test_validate_ticker_uppercases() -> None:
    assert validate_ticker(" aapl ") == "AAPL"


def test_validate_ticker_rejects_invalid_symbol() -> None:
    with pytest.raises(WatchlistTickerInvalidError):
        validate_ticker("AAPL!")


def test_validate_bars_query_rejects_extended_sessions() -> None:
    with pytest.raises(MarketBarsSessionUnsupportedError):
        validate_bars_query(
            ticker="AAPL",
            resolution="1m",
            session="pre_market",
            adjustment="split_adjusted",
            fill="none",
            include_partial=True,
            from_time=datetime(2026, 4, 15, 13, 30, tzinfo=UTC),
            to_time=datetime(2026, 4, 15, 13, 35, tzinfo=UTC),
            count_back=None,
        )
