"""Domain rule tests."""

from __future__ import annotations

import pytest

from domain.exceptions import WatchlistTickerInvalidError
from domain.rules import normalize_email, validate_ticker


def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  USER@Example.COM ") == "user@example.com"


def test_validate_ticker_uppercases() -> None:
    assert validate_ticker(" aapl ") == "AAPL"


def test_validate_ticker_rejects_invalid_symbol() -> None:
    with pytest.raises(WatchlistTickerInvalidError):
        validate_ticker("AAPL!")
