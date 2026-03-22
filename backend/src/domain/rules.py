"""Pure domain rules and normalization helpers."""

from __future__ import annotations

import re

from domain.exceptions import WatchlistTickerInvalidError


WATCHLIST_ITEM_LIMIT = 50
TICKER_PATTERN = re.compile(r"^[A-Z0-9.-]{1,15}$")


def normalize_email(email: str) -> str:
    """Normalize email for identity comparisons."""
    return email.strip().lower()


def normalize_ticker(ticker: str) -> str:
    """Normalize ticker to the canonical persisted representation."""
    return ticker.strip().upper()


def validate_ticker(ticker: str) -> str:
    """Validate and normalize a ticker symbol."""
    normalized = normalize_ticker(ticker)
    if not TICKER_PATTERN.fullmatch(normalized):
        raise WatchlistTickerInvalidError()
    return normalized
