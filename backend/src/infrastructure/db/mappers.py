"""ORM to domain entity mappers."""

from __future__ import annotations

from datetime import UTC, datetime

from domain.entities import CanonicalBar, Snapshot, TickerBarsState, User, WatchlistItem
from infrastructure.db.models import (
    MarketBar1dModel,
    MarketBar1mModel,
    MarketTerminalSnapshotModel,
    MarketTickerBarsStateModel,
    UserModel,
    WatchlistItemModel,
)


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


def to_market_bar_1m_entity(model: MarketBar1mModel) -> CanonicalBar:
    """Map a 1m ORM model to a canonical bar entity."""
    return CanonicalBar(
        ticker=model.ticker,
        adjustment=model.adjustment,
        granularity="1m",
        bucket_start_at=_ensure_utc(model.bucket_start_at_utc),
        trading_day=model.trading_day,
        session_kind=model.session_kind,
        open=model.open,
        high=model.high,
        low=model.low,
        close=model.close,
        volume=model.volume,
        vw=model.vw,
        trade_count=model.trade_count,
        provider_updated_at=_ensure_utc(model.provider_updated_at),
        is_final=model.is_final,
        first_synced_at=_ensure_utc(model.first_synced_at),
        last_synced_at=_ensure_utc(model.last_synced_at),
    )


def to_market_bar_1d_entity(model: MarketBar1dModel) -> CanonicalBar:
    """Map a 1d ORM model to a canonical bar entity."""
    return CanonicalBar(
        ticker=model.ticker,
        adjustment=model.adjustment,
        granularity="1d",
        bucket_start_at=_ensure_utc(model.bucket_start_at_utc),
        trading_day=model.trading_day,
        session_kind="regular",
        open=model.open,
        high=model.high,
        low=model.low,
        close=model.close,
        volume=model.volume,
        vw=model.vw,
        trade_count=model.trade_count,
        provider_updated_at=_ensure_utc(model.provider_updated_at),
        is_final=True,
        first_synced_at=_ensure_utc(model.first_synced_at),
        last_synced_at=_ensure_utc(model.last_synced_at),
    )


def to_market_ticker_bars_state_entity(model: MarketTickerBarsStateModel) -> TickerBarsState:
    """Map ticker bars readiness ORM model to a domain entity."""
    return TickerBarsState(
        ticker=model.ticker,
        status=model.status,
        bootstrap_requested_at=_ensure_utc(model.bootstrap_requested_at) if model.bootstrap_requested_at is not None else None,
        bootstrap_started_at=_ensure_utc(model.bootstrap_started_at) if model.bootstrap_started_at is not None else None,
        bootstrap_finished_at=_ensure_utc(model.bootstrap_finished_at) if model.bootstrap_finished_at is not None else None,
        bootstrap_failed_at=_ensure_utc(model.bootstrap_failed_at) if model.bootstrap_failed_at is not None else None,
        last_reconciled_at=_ensure_utc(model.last_reconciled_at) if model.last_reconciled_at is not None else None,
        earliest_1m_trading_day=model.earliest_1m_trading_day,
        last_1m_trading_day=model.last_1m_trading_day,
        last_1m_bucket_start_at=_ensure_utc(model.last_1m_bucket_start_at) if model.last_1m_bucket_start_at is not None else None,
        earliest_1d_trading_day=model.earliest_1d_trading_day,
        latest_1d_trading_day=model.latest_1d_trading_day,
        last_error_code=model.last_error_code,
        last_error_message=model.last_error_message,
        created_at=_ensure_utc(model.created_at),
        updated_at=_ensure_utc(model.updated_at),
    )


def to_market_terminal_snapshot_entity(model: MarketTerminalSnapshotModel) -> Snapshot:
    """Map a terminal snapshot ORM model to a snapshot entity."""
    return Snapshot(
        ticker=model.ticker,
        last=model.last,
        regular_close=model.regular_close,
        change=model.change,
        change_pct=model.change_pct,
        open=model.open,
        high=model.high,
        low=model.low,
        volume=model.volume,
        prev_close=model.prev_close,
        market_status=model.market_status,
        session=model.session,
        trading_day=model.trading_day,
        last_session=model.last_session,
        last_trade_at=_ensure_utc(model.last_trade_at) if model.last_trade_at is not None else None,
        delay_minutes=model.delay_minutes,
        is_realtime=model.is_realtime,
        provider_updated_at=_ensure_utc(model.provider_updated_at),
        fetched_at=_ensure_utc(model.fetched_at),
        data_source=model.data_source,
    )
