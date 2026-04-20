"""Pure domain rules and normalization helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from domain.entities import BarsQuery, MarketDataMode
from domain.exceptions import (
    MarketBarsAdjustmentUnsupportedError,
    MarketBarsCountBackInvalidError,
    MarketBarsCountBackTooLargeError,
    MarketBarsQueryModeInvalidError,
    MarketBarsRangeInvalidError,
    MarketBarsResolutionUnsupportedError,
    MarketBarsSessionUnsupportedError,
    MarketBarsUnsupportedSessionResolutionError,
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
SUPPORTED_BARS_RESOLUTIONS = frozenset({"1m", "5m", "15m", "30m", "60m", "1D", "1W", "1M", "1Q"})
SUPPORTED_BARS_SESSIONS = frozenset({"pre_market", "regular", "after_hours"})
SUPPORTED_BARS_ADJUSTMENTS = frozenset({"split_adjusted"})
SUPPORTED_BARS_FILLS = frozenset({"carry_forward", "none"})
TICKER_BARS_READINESS_STATES = frozenset({"pending", "initializing", "ready", "degraded", "failed"})
MARKET_BARS_MAX_COUNT_BACK = 2_000
MARKET_BARS_MAX_ESTIMATED_OUTPUT_ROWS = 5_000
MARKET_BARS_1M_RETENTION_TRADING_DAYS = 10
MARKET_BARS_1D_RETENTION_YEARS = 10


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


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def validate_bars_query(
    *,
    ticker: str,
    resolution: str,
    session: str,
    adjustment: str,
    fill: str,
    include_partial: bool,
    from_time: datetime | None,
    to_time: datetime | None,
    count_back: int | None,
) -> BarsQuery:
    normalized_ticker = validate_market_data_ticker(ticker)

    if resolution not in SUPPORTED_BARS_RESOLUTIONS:
        raise MarketBarsResolutionUnsupportedError()
    if session not in SUPPORTED_BARS_SESSIONS:
        raise MarketBarsSessionUnsupportedError()
    if adjustment not in SUPPORTED_BARS_ADJUSTMENTS:
        raise MarketBarsAdjustmentUnsupportedError()
    if fill not in SUPPORTED_BARS_FILLS:
        raise ValidationError(detail="fill: Expected one of carry_forward, none.")
    if resolution in {"1W", "1M", "1Q"} and session != "regular":
        raise MarketBarsUnsupportedSessionResolutionError()

    normalized_from = _ensure_utc(from_time) if from_time is not None else None
    normalized_to = _ensure_utc(to_time) if to_time is not None else None

    if normalized_from is not None and normalized_to is None:
        raise MarketBarsQueryModeInvalidError(detail="to: Required when from is provided.")
    if normalized_from is None and normalized_to is None and count_back is None:
        # allow service defaults only for higher timeframe latest mode
        pass
    if normalized_from is not None and count_back is not None:
        raise MarketBarsQueryModeInvalidError()
    if normalized_from is not None and normalized_to is not None and normalized_from >= normalized_to:
        raise MarketBarsRangeInvalidError()
    if count_back is not None and count_back <= 0:
        raise MarketBarsCountBackInvalidError()
    if count_back is not None and count_back > MARKET_BARS_MAX_COUNT_BACK:
        raise MarketBarsCountBackTooLargeError()

    return BarsQuery(
        ticker=normalized_ticker,
        resolution=resolution,
        session=session,
        adjustment=adjustment,
        fill=fill,
        include_partial=include_partial,
        from_time=normalized_from,
        to_time=normalized_to,
        count_back=count_back,
    )
