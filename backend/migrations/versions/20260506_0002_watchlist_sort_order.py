"""Add watchlist sort order.

Revision ID: 20260506_0002
Revises: 20260426_0001
Create Date: 2026-05-06 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260506_0002"
down_revision: str | None = "20260426_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watchlist_items",
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_watchlist_items_user_sort_order",
        "watchlist_items",
        ["user_id", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_user_sort_order", table_name="watchlist_items")
    op.drop_column("watchlist_items", "sort_order")
