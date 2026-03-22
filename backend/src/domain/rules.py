"""Pure domain rules and normalization helpers."""

from __future__ import annotations

import re

from domain.exceptions import ValidationError, WatchlistTickerInvalidError


WATCHLIST_ITEM_LIMIT = 50
MIN_PASSWORD_LENGTH = 8
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


def validate_password(password: str) -> str:
    """Validate a registration password."""
    if not password.strip() or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(detail=f"password: String should have at least {MIN_PASSWORD_LENGTH} characters")
    return password
