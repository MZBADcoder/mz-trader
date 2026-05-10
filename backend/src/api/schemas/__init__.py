"""API schema exports."""

from api.schemas.auth import (
    AuthSessionResponse,
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from api.schemas.error import ErrorBody, ErrorResponse
from api.schemas.health import HealthResponse
from api.schemas.ticker_search import TickerSearchItemResponse, TickerSearchResponse
from api.schemas.watchlist import (
    CreateWatchlistItemRequest,
    CreateWatchlistItemResponse,
    UpdateWatchlistRequest,
    WatchlistItemResponse,
    WatchlistResponse,
)


__all__ = [
    "AuthSessionResponse",
    "CreateWatchlistItemRequest",
    "CreateWatchlistItemResponse",
    "CurrentUserResponse",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "LoginRequest",
    "RegisterRequest",
    "TickerSearchItemResponse",
    "TickerSearchResponse",
    "UpdateWatchlistRequest",
    "UserResponse",
    "WatchlistItemResponse",
    "WatchlistResponse",
]
