"""Shared helpers for snapshot session context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from domain.entities import Snapshot
from infrastructure.calendar import UsStockCalendar


@dataclass(slots=True)
class SnapshotSessionContext:
    """Product session context for one snapshot refresh or query."""

    session: str
    trading_day: date
    active: bool


def build_snapshot_session_context(
    *,
    calendar: UsStockCalendar,
    effective_now: datetime,
) -> SnapshotSessionContext:
    """Return the product session context for snapshot behavior."""
    effective_now = _ensure_utc(effective_now)
    market_day = calendar.to_market_date(effective_now)
    if not calendar.is_trading_day(market_day):
        return SnapshotSessionContext(
            session="closed",
            trading_day=calendar.previous_or_same_trading_day(market_day),
            active=False,
        )

    pre_window = calendar.session_window(market_day, "pre_market")
    regular_window = calendar.session_window(market_day, "regular")
    after_window = calendar.session_window(market_day, "after_hours")
    if effective_now < pre_window.start_at:
        return SnapshotSessionContext(
            session="closed",
            trading_day=calendar.previous_trading_day(market_day),
            active=False,
        )
    if effective_now < regular_window.start_at:
        return SnapshotSessionContext(session="pre_market", trading_day=market_day, active=True)
    if effective_now < regular_window.end_at:
        return SnapshotSessionContext(session="regular", trading_day=market_day, active=True)
    if effective_now <= after_window.end_at:
        return SnapshotSessionContext(session="after_hours", trading_day=market_day, active=True)
    return SnapshotSessionContext(session="closed", trading_day=market_day, active=False)


def attach_snapshot_session_context(
    *,
    snapshot: Snapshot,
    context: SnapshotSessionContext,
    calendar: UsStockCalendar,
) -> Snapshot:
    """Attach product session metadata to a provider or cached snapshot."""
    last_session = None
    if snapshot.last_trade_at is not None:
        _, last_session = calendar.classify_session(snapshot.last_trade_at)
    return replace(
        snapshot,
        session=context.session,
        trading_day=context.trading_day,
        last_session=last_session,
    )


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
