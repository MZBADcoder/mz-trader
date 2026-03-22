"""Watchlist DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateWatchlistItemRequest(BaseModel):
    """Payload for adding a watchlist item."""

    ticker: str


class WatchlistItemResponse(BaseModel):
    """Watchlist item returned to the client."""

    ticker: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WatchlistResponse(BaseModel):
    """Response envelope for listing the watchlist."""

    items: list[WatchlistItemResponse]

    model_config = ConfigDict(from_attributes=True)


class CreateWatchlistItemResponse(BaseModel):
    """Response envelope for a newly created watchlist item."""

    item: WatchlistItemResponse

    model_config = ConfigDict(from_attributes=True)
