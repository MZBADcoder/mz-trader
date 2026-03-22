"""API schema exports."""

from api.schemas.auth import AuthRequest, AuthSessionResponse, CurrentUserResponse, UserResponse
from api.schemas.error import ErrorBody, ErrorResponse
from api.schemas.health import HealthResponse
from api.schemas.reference import TickerSearchItemResponse, TickerSearchResponse
from api.schemas.watchlist import (
    CreateWatchlistItemRequest,
    CreateWatchlistItemResponse,
    WatchlistItemResponse,
    WatchlistResponse,
)


__all__ = [
    "AuthRequest",
    "AuthSessionResponse",
    "CreateWatchlistItemRequest",
    "CreateWatchlistItemResponse",
    "CurrentUserResponse",
    "ErrorBody",
    "ErrorResponse",
    "HealthResponse",
    "TickerSearchItemResponse",
    "TickerSearchResponse",
    "UserResponse",
    "WatchlistItemResponse",
    "WatchlistResponse",
]
