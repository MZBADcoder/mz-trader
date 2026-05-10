"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


class UserModel(Base):
    """Persisted user record."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WatchlistItemModel(Base):
    """Persisted watchlist item."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", name="uq_watchlist_items_user_ticker"),
        Index("ix_watchlist_items_user_id", "user_id"),
        Index("ix_watchlist_items_user_sort_order", "user_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(15), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MarketBar1mModel(Base):
    """Canonical provider-truth minute bars."""

    __tablename__ = "market_bars_1m"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "adjustment",
            "bucket_start_at_utc",
            name="uq_market_bars_1m_ticker_adjustment_bucket_start_at_utc",
        ),
        Index(
            "ix_market_bars_1m_ticker_adjustment_bucket_start_at_utc",
            "ticker",
            "adjustment",
            "bucket_start_at_utc",
        ),
        Index(
            "ix_mkt_bars_1m_ticker_adj_day_session_bucket",
            "ticker",
            "adjustment",
            "trading_day",
            "session_kind",
            "bucket_start_at_utc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(15), nullable=False)
    adjustment: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket_start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    session_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    open: Mapped[float] = mapped_column(nullable=False)
    high: Mapped[float] = mapped_column(nullable=False)
    low: Mapped[float] = mapped_column(nullable=False)
    close: Mapped[float] = mapped_column(nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    vw: Mapped[float | None] = mapped_column(nullable=True)
    trade_count: Mapped[int] = mapped_column(nullable=False)
    provider_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketBar1dModel(Base):
    """Canonical completed regular daily bars."""

    __tablename__ = "market_bars_1d"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "adjustment",
            "trading_day",
            name="uq_market_bars_1d_ticker_adjustment_trading_day",
        ),
        Index(
            "ix_market_bars_1d_ticker_adjustment_bucket_start_at_utc",
            "ticker",
            "adjustment",
            "bucket_start_at_utc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(15), nullable=False)
    adjustment: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    bucket_start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(nullable=False)
    high: Mapped[float] = mapped_column(nullable=False)
    low: Mapped[float] = mapped_column(nullable=False)
    close: Mapped[float] = mapped_column(nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    vw: Mapped[float | None] = mapped_column(nullable=True)
    trade_count: Mapped[int] = mapped_column(nullable=False)
    provider_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketTickerBarsStateModel(Base):
    """Ticker-level bars readiness and maintenance state."""

    __tablename__ = "market_ticker_bars_state"
    __table_args__ = (
        Index("ix_market_ticker_bars_state_status", "status"),
    )

    ticker: Mapped[str] = mapped_column(String(15), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    bootstrap_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bootstrap_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bootstrap_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bootstrap_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    earliest_1m_trading_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_1m_trading_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_1m_bucket_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    earliest_1d_trading_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_1d_trading_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class MarketTerminalSnapshotModel(Base):
    """Terminal snapshot captured after the trading day's after-hours session."""

    __tablename__ = "market_terminal_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "trading_day",
            name="uq_market_terminal_snapshots_ticker_trading_day",
        ),
        Index(
            "ix_market_terminal_snapshots_ticker_trading_day",
            "ticker",
            "trading_day",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(15), nullable=False)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    last: Mapped[float] = mapped_column(nullable=False)
    regular_close: Mapped[float] = mapped_column(nullable=False)
    change: Mapped[float] = mapped_column(nullable=False)
    change_pct: Mapped[float] = mapped_column(nullable=False)
    open: Mapped[float] = mapped_column(nullable=False)
    high: Mapped[float] = mapped_column(nullable=False)
    low: Mapped[float] = mapped_column(nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    prev_close: Mapped[float] = mapped_column(nullable=False)
    market_status: Mapped[str] = mapped_column(String(32), nullable=False)
    session: Mapped[str] = mapped_column(String(32), nullable=False)
    last_session: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_trade_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_minutes: Mapped[int] = mapped_column(nullable=False)
    is_realtime: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_source: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
