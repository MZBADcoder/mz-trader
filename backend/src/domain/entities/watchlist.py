"""Watchlist domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class WatchlistItem:
    """Single watchlist item bound to a user."""

    id: str
    user_id: str
    ticker: str
    position: int
    created_at: datetime
