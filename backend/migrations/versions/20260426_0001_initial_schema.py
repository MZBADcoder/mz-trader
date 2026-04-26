"""Initial database schema.

Revision ID: 20260426_0001
Revises:
Create Date: 2026-04-26 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260426_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_bars_1d",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=15), nullable=False),
        sa.Column("adjustment", sa.String(length=32), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("bucket_start_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("vw", sa.Float(), nullable=True),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker",
            "adjustment",
            "trading_day",
            name="uq_market_bars_1d_ticker_adjustment_trading_day",
        ),
    )
    op.create_index(
        "ix_market_bars_1d_ticker_adjustment_bucket_start_at_utc",
        "market_bars_1d",
        ["ticker", "adjustment", "bucket_start_at_utc"],
        unique=False,
    )

    op.create_table(
        "market_bars_1m",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=15), nullable=False),
        sa.Column("adjustment", sa.String(length=32), nullable=False),
        sa.Column("bucket_start_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("session_kind", sa.String(length=32), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("vw", sa.Float(), nullable=True),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("first_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker",
            "adjustment",
            "bucket_start_at_utc",
            name="uq_market_bars_1m_ticker_adjustment_bucket_start_at_utc",
        ),
    )
    op.create_index(
        "ix_market_bars_1m_ticker_adjustment_bucket_start_at_utc",
        "market_bars_1m",
        ["ticker", "adjustment", "bucket_start_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_mkt_bars_1m_ticker_adj_day_session_bucket",
        "market_bars_1m",
        ["ticker", "adjustment", "trading_day", "session_kind", "bucket_start_at_utc"],
        unique=False,
    )

    op.create_table(
        "market_terminal_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=15), nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("last", sa.Float(), nullable=False),
        sa.Column("regular_close", sa.Float(), nullable=False),
        sa.Column("change", sa.Float(), nullable=False),
        sa.Column("change_pct", sa.Float(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("prev_close", sa.Float(), nullable=False),
        sa.Column("market_status", sa.String(length=32), nullable=False),
        sa.Column("session", sa.String(length=32), nullable=False),
        sa.Column("last_session", sa.String(length=32), nullable=True),
        sa.Column("last_trade_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("is_realtime", sa.Boolean(), nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ticker",
            "trading_day",
            name="uq_market_terminal_snapshots_ticker_trading_day",
        ),
    )
    op.create_index(
        "ix_market_terminal_snapshots_ticker_trading_day",
        "market_terminal_snapshots",
        ["ticker", "trading_day"],
        unique=False,
    )

    op.create_table(
        "market_ticker_bars_state",
        sa.Column("ticker", sa.String(length=15), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("bootstrap_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bootstrap_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bootstrap_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bootstrap_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("earliest_1m_trading_day", sa.Date(), nullable=True),
        sa.Column("last_1m_trading_day", sa.Date(), nullable=True),
        sa.Column("last_1m_bucket_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("earliest_1d_trading_day", sa.Date(), nullable=True),
        sa.Column("latest_1d_trading_day", sa.Date(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("ticker"),
    )
    op.create_index(
        "ix_market_ticker_bars_state_status",
        "market_ticker_bars_state",
        ["status"],
        unique=False,
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ticker", name="uq_watchlist_items_user_ticker"),
    )
    op.create_index("ix_watchlist_items_user_id", "watchlist_items", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_user_id", table_name="watchlist_items")
    op.drop_table("watchlist_items")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_market_ticker_bars_state_status", table_name="market_ticker_bars_state")
    op.drop_table("market_ticker_bars_state")
    op.drop_index("ix_market_terminal_snapshots_ticker_trading_day", table_name="market_terminal_snapshots")
    op.drop_table("market_terminal_snapshots")
    op.drop_index("ix_mkt_bars_1m_ticker_adj_day_session_bucket", table_name="market_bars_1m")
    op.drop_index("ix_market_bars_1m_ticker_adjustment_bucket_start_at_utc", table_name="market_bars_1m")
    op.drop_table("market_bars_1m")
    op.drop_index("ix_market_bars_1d_ticker_adjustment_bucket_start_at_utc", table_name="market_bars_1d")
    op.drop_table("market_bars_1d")
