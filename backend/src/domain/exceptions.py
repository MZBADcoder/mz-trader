"""Domain exception definitions."""

from __future__ import annotations


class AppError(Exception):
    """Stable application error surfaced to the API layer."""

    code = "INTERNAL_ERROR"
    message = "Internal server error."
    detail = ""
    status_code = 500

    def __init__(self, *, detail: str = "") -> None:
        self.detail = detail or self.detail
        super().__init__(self.message)


class ValidationError(AppError):
    """Request validation failed."""

    code = "VALIDATION_ERROR"
    message = "Request validation failed."
    status_code = 400


class AuthenticationRequiredError(AppError):
    """Authentication is required."""

    code = "AUTH_REQUIRED"
    message = "Authentication is required."
    status_code = 401


class AuthTokenInvalidError(AppError):
    """Token cannot be trusted."""

    code = "AUTH_TOKEN_INVALID"
    message = "Authentication token is invalid."
    status_code = 401


class AuthTokenExpiredError(AppError):
    """Token is expired."""

    code = "AUTH_TOKEN_EXPIRED"
    message = "Authentication token has expired."
    status_code = 401


class AuthInvalidCredentialsError(AppError):
    """Email or password is incorrect."""

    code = "AUTH_INVALID_CREDENTIALS"
    message = "Email or password is incorrect."
    status_code = 401


class AuthEmailAlreadyExistsError(AppError):
    """Email is already registered."""

    code = "AUTH_EMAIL_ALREADY_EXISTS"
    message = "Email is already registered."
    status_code = 409


class WatchlistTickerInvalidError(AppError):
    """Ticker format is invalid."""

    code = "WATCHLIST_TICKER_INVALID"
    message = "Ticker format is invalid."
    status_code = 422


class WatchlistTickerNotSupportedError(AppError):
    """Ticker does not exist in upstream reference data."""

    code = "WATCHLIST_TICKER_NOT_SUPPORTED"
    message = "Ticker is not supported."
    status_code = 422


class WatchlistTickerDuplicateError(AppError):
    """Ticker already exists in the watchlist."""

    code = "WATCHLIST_TICKER_DUPLICATE"
    message = "Ticker already exists in the watchlist."
    status_code = 409


class WatchlistTickerNotFoundError(AppError):
    """Ticker is not in the watchlist."""

    code = "WATCHLIST_TICKER_NOT_FOUND"
    message = "Ticker was not found in the watchlist."
    status_code = 404


class WatchlistLimitExceededError(AppError):
    """Watchlist item count exceeds the limit."""

    code = "WATCHLIST_LIMIT_EXCEEDED"
    message = "Watchlist limit exceeded."
    status_code = 409


class WatchlistOrderInvalidError(AppError):
    """Watchlist reorder payload is not a valid permutation."""

    code = "WATCHLIST_ORDER_INVALID"
    message = "Watchlist order is invalid."
    status_code = 422


class MarketDataTickerInvalidError(AppError):
    """Market data ticker format is invalid."""

    code = "MARKET_DATA_TICKER_INVALID"
    message = "Ticker format is invalid."
    status_code = 422


class MarketDataTickerLimitExceededError(AppError):
    """Snapshot request exceeds the supported ticker count."""

    code = "MARKET_DATA_TICKER_LIMIT_EXCEEDED"
    message = "Ticker limit exceeded."
    status_code = 409


class MarketSnapshotUpstreamUnavailableError(AppError):
    """Upstream market data provider is unavailable."""

    code = "MARKET_SNAPSHOT_UPSTREAM_UNAVAILABLE"
    message = "Market snapshot provider is unavailable."
    status_code = 503


class MarketBarsResolutionUnsupportedError(AppError):
    """Requested chart resolution is not supported."""

    code = "MARKET_BARS_RESOLUTION_UNSUPPORTED"
    message = "Chart resolution is not supported."
    status_code = 422


class MarketBarsSessionUnsupportedError(AppError):
    """Requested chart session is not supported."""

    code = "MARKET_BARS_SESSION_UNSUPPORTED"
    message = "Chart session is not supported."
    status_code = 422


class MarketBarsUnsupportedSessionResolutionError(AppError):
    """Requested session + resolution combination is not supported."""

    code = "MARKET_BARS_UNSUPPORTED_SESSION_RESOLUTION"
    message = "Chart session and resolution combination is not supported."
    status_code = 422


class MarketBarsRangeInvalidError(AppError):
    """Requested chart range is invalid."""

    code = "MARKET_BARS_RANGE_INVALID"
    message = "Chart range is invalid."
    status_code = 422


class MarketBarsCountBackInvalidError(AppError):
    """Requested count_back is invalid."""

    code = "MARKET_BARS_COUNT_BACK_INVALID"
    message = "count_back is invalid."
    status_code = 422


class MarketBarsCountBackTooLargeError(AppError):
    """Requested count_back exceeds the supported cap."""

    code = "MARKET_BARS_COUNT_BACK_TOO_LARGE"
    message = "count_back is too large."
    status_code = 422


class MarketBarsQueryModeInvalidError(AppError):
    """The bars query mixes unsupported query mode parameters."""

    code = "MARKET_BARS_QUERY_MODE_INVALID"
    message = "Chart query mode is invalid."
    status_code = 422


class MarketBarsRangeTooLargeError(AppError):
    """The requested bars range is too large."""

    code = "MARKET_BARS_RANGE_TOO_LARGE"
    message = "Chart range is too large."
    status_code = 422


class MarketBarsAdjustmentUnsupportedError(AppError):
    """The requested adjustment mode is not implemented."""

    code = "MARKET_BARS_ADJUSTMENT_UNSUPPORTED"
    message = "Chart adjustment mode is not supported."
    status_code = 422


class MarketBarsUpstreamUnavailableError(AppError):
    """Upstream bars provider is unavailable."""

    code = "MARKET_BARS_UPSTREAM_UNAVAILABLE"
    message = "Market bars provider is unavailable."
    status_code = 503


class InternalError(AppError):
    """Internal service failure with a stable outward-facing payload."""

    code = "INTERNAL_ERROR"
    message = "Internal server error."
    status_code = 500
