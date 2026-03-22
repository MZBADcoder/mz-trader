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


class InternalError(AppError):
    """Internal service failure with a stable outward-facing payload."""

    code = "INTERNAL_ERROR"
    message = "Internal server error."
    status_code = 500
