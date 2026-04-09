"""Pure domain rules and normalization helpers."""

from __future__ import annotations

import re

from domain.entities import MarketDataMode
from domain.exceptions import (
    MarketDataTickerInvalidError,
    MarketDataTickerLimitExceededError,
    ValidationError,
    WatchlistTickerInvalidError,
)


WATCHLIST_ITEM_LIMIT = 50
MARKET_DATA_REQUEST_TICKER_LIMIT = 50
MIN_PASSWORD_LENGTH = 8
TICKER_PATTERN = re.compile(r"^[A-Z0-9.-]{1,15}$")
SUPPORTED_MARKET_DATA_DELAY_MINUTES = frozenset({0, 15})


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


def validate_market_data_ticker(ticker: str) -> str:
    """Validate a ticker for market-data APIs."""
    normalized = normalize_ticker(ticker)
    if not TICKER_PATTERN.fullmatch(normalized):
        raise MarketDataTickerInvalidError()
    return normalized


def validate_market_data_tickers(
    tickers: list[str],
    *,
    limit: int = MARKET_DATA_REQUEST_TICKER_LIMIT,
) -> list[str]:
    """Validate, normalize, and deduplicate requested tickers."""
    normalized: list[str] = []
    seen: set[str] = set()

    for ticker in tickers:
        candidate = validate_market_data_ticker(ticker)
        if candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)

    if not normalized:
        raise ValidationError(detail="tickers: At least one ticker is required.")

    if len(normalized) > limit:
        raise MarketDataTickerLimitExceededError(
            detail=f"tickers: At most {limit} unique tickers are allowed."
        )

    return normalized


def build_market_data_mode(*, delay_minutes: int, supports_stream: bool = False) -> MarketDataMode:
    """Validate and resolve the runtime market-data mode."""
    if delay_minutes not in SUPPORTED_MARKET_DATA_DELAY_MINUTES:
        supported = ", ".join(str(value) for value in sorted(SUPPORTED_MARKET_DATA_DELAY_MINUTES))
        raise ValidationError(detail=f"market_data_delay_minutes: Expected one of {supported}.")
    return MarketDataMode(delay_minutes=delay_minutes, supports_stream=supports_stream)


def validate_password(password: str) -> str:
    """Validate a registration password."""
    if not password.strip() or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(detail=f"password: String should have at least {MIN_PASSWORD_LENGTH} characters")
    return password
