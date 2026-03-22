"""ORM to domain entity mappers."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.entities import User, WatchlistItem
from infrastructure.db.models import UserModel, WatchlistItemModel


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_user_entity(model: UserModel) -> User:
    """Map a user ORM model to a domain entity."""
    return User(
        id=str(model.id),
        email=model.email,
        password_hash=model.password_hash,
        created_at=_ensure_utc(model.created_at),
        updated_at=_ensure_utc(model.updated_at),
    )


def to_watchlist_item_entity(model: WatchlistItemModel) -> WatchlistItem:
    """Map a watchlist ORM model to a domain entity."""
    return WatchlistItem(
        id=str(model.id),
        user_id=str(model.user_id),
        ticker=model.ticker,
        created_at=_ensure_utc(model.created_at),
    )
