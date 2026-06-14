"""Shared helpers for bars bootstrap, refresh, reconciliation, and cleanup."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from domain.entities import CanonicalBar, ProviderBar, TickerBarsState
from infrastructure.calendar import UsStockCalendar


def build_canonical_1m_rows(
    *,
    ticker: str,
    adjustment: str,
    provider_bars: list[ProviderBar],
    calendar: UsStockCalendar,
    effective_now: datetime,
    synced_at: datetime,
) -> list[CanonicalBar]:
    rows: list[CanonicalBar] = []
    for provider_bar in provider_bars:
        trading_day, session_kind = calendar.classify_session(provider_bar.time)
        if session_kind != "regular":
            continue
        rows.append(
            CanonicalBar(
                ticker=ticker,
                adjustment=adjustment,
                granularity="1m",
                bucket_start_at=provider_bar.time,
                trading_day=trading_day,
                session_kind=session_kind,
                open=provider_bar.open,
                high=provider_bar.high,
                low=provider_bar.low,
                close=provider_bar.close,
                volume=provider_bar.volume,
                vw=provider_bar.vw,
                trade_count=provider_bar.trade_count,
                provider_updated_at=provider_bar.provider_updated_at,
                is_final=provider_bar.time + timedelta(minutes=1) <= effective_now,
                first_synced_at=synced_at,
                last_synced_at=synced_at,
            )
        )
    return rows


def aggregate_daily_row(
    *,
    ticker: str,
    adjustment: str,
    trading_day: date,
    bucket_start_at: datetime,
    rows: list[CanonicalBar],
    synced_at: datetime,
) -> CanonicalBar:
    weighted_total = 0.0
    total_volume = 0
    for row in rows:
        if row.vw is None or row.volume <= 0:
            continue
        weighted_total += row.vw * row.volume
        total_volume += row.volume
    return CanonicalBar(
        ticker=ticker,
        adjustment=adjustment,
        granularity="1d",
        bucket_start_at=bucket_start_at,
        trading_day=trading_day,
        session_kind="regular",
        open=rows[0].open,
        high=max(row.high for row in rows),
        low=min(row.low for row in rows),
        close=rows[-1].close,
        volume=sum(row.volume for row in rows),
        vw=(weighted_total / total_volume) if total_volume > 0 else None,
        trade_count=sum(row.trade_count for row in rows),
        provider_updated_at=max(row.provider_updated_at for row in rows),
        is_final=True,
        first_synced_at=synced_at,
        last_synced_at=synced_at,
    )


def build_ready_state(
    *,
    ticker: str,
    now: datetime,
    minute_rows: list[CanonicalBar],
    daily_rows: list[CanonicalBar],
    existing: TickerBarsState | None,
) -> TickerBarsState:
    earliest_1m = _min_optional_date(
        minute_rows[0].trading_day if minute_rows else None,
        existing.earliest_1m_trading_day if existing else None,
    )
    last_1m = _max_optional_date(
        minute_rows[-1].trading_day if minute_rows else None,
        existing.last_1m_trading_day if existing else None,
    )
    last_1m_bucket = _max_optional_datetime(
        minute_rows[-1].bucket_start_at if minute_rows else None,
        existing.last_1m_bucket_start_at if existing else None,
    )
    earliest_1d = _min_optional_date(
        daily_rows[0].trading_day if daily_rows else None,
        existing.earliest_1d_trading_day if existing else None,
    )
    latest_1d = _max_optional_date(
        daily_rows[-1].trading_day if daily_rows else None,
        existing.latest_1d_trading_day if existing else None,
    )
    created_at = existing.created_at if existing is not None else now
    bootstrap_requested_at = existing.bootstrap_requested_at if existing is not None else now
    bootstrap_started_at = existing.bootstrap_started_at if existing is not None else now
    return TickerBarsState(
        ticker=ticker,
        status="ready",
        bootstrap_requested_at=bootstrap_requested_at,
        bootstrap_started_at=bootstrap_started_at,
        bootstrap_finished_at=now,
        bootstrap_failed_at=None,
        last_reconciled_at=now,
        earliest_1m_trading_day=earliest_1m,
        last_1m_trading_day=last_1m,
        last_1m_bucket_start_at=last_1m_bucket,
        earliest_1d_trading_day=earliest_1d,
        latest_1d_trading_day=latest_1d,
        last_error_code=None,
        last_error_message=None,
        created_at=created_at,
        updated_at=now,
    )


def clamp_state_to_retention(
    *,
    state: TickerBarsState,
    minute_threshold_day: date,
    daily_threshold_day: date,
    now: datetime,
) -> TickerBarsState:
    earliest_1m = state.earliest_1m_trading_day
    last_1m = state.last_1m_trading_day
    last_1m_bucket = state.last_1m_bucket_start_at
    if last_1m is not None and last_1m < minute_threshold_day:
        earliest_1m = None
        last_1m = None
        last_1m_bucket = None
    elif earliest_1m is not None and earliest_1m < minute_threshold_day:
        earliest_1m = minute_threshold_day

    earliest_1d = state.earliest_1d_trading_day
    latest_1d = state.latest_1d_trading_day
    if latest_1d is not None and latest_1d < daily_threshold_day:
        earliest_1d = None
        latest_1d = None
    elif earliest_1d is not None and earliest_1d < daily_threshold_day:
        earliest_1d = daily_threshold_day

    return replace(
        state,
        earliest_1m_trading_day=earliest_1m,
        last_1m_trading_day=last_1m,
        last_1m_bucket_start_at=last_1m_bucket,
        earliest_1d_trading_day=earliest_1d,
        latest_1d_trading_day=latest_1d,
        updated_at=now,
    )


def clamp_state_to_regular_1m_bounds(
    *,
    state: TickerBarsState,
    regular_bounds: tuple[date, date, datetime] | None,
    now: datetime,
) -> TickerBarsState:
    if regular_bounds is None:
        return replace(
            state,
            earliest_1m_trading_day=None,
            last_1m_trading_day=None,
            last_1m_bucket_start_at=None,
            updated_at=now,
        )
    earliest_1m, last_1m, last_1m_bucket = regular_bounds
    return replace(
        state,
        earliest_1m_trading_day=earliest_1m,
        last_1m_trading_day=last_1m,
        last_1m_bucket_start_at=last_1m_bucket,
        updated_at=now,
    )


def build_initializing_state(*, ticker: str, now: datetime, existing: TickerBarsState | None) -> TickerBarsState:
    created_at = existing.created_at if existing is not None else now
    requested_at = existing.bootstrap_requested_at if existing is not None else now
    return TickerBarsState(
        ticker=ticker,
        status="initializing",
        bootstrap_requested_at=requested_at,
        bootstrap_started_at=now,
        bootstrap_finished_at=existing.bootstrap_finished_at if existing is not None else None,
        bootstrap_failed_at=existing.bootstrap_failed_at if existing is not None else None,
        last_reconciled_at=existing.last_reconciled_at if existing is not None else None,
        earliest_1m_trading_day=existing.earliest_1m_trading_day if existing is not None else None,
        last_1m_trading_day=existing.last_1m_trading_day if existing is not None else None,
        last_1m_bucket_start_at=existing.last_1m_bucket_start_at if existing is not None else None,
        earliest_1d_trading_day=existing.earliest_1d_trading_day if existing is not None else None,
        latest_1d_trading_day=existing.latest_1d_trading_day if existing is not None else None,
        last_error_code=None,
        last_error_message=None,
        created_at=created_at,
        updated_at=now,
    )


def utc_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _min_optional_date(left: date | None, right: date | None) -> date | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _max_optional_date(left: date | None, right: date | None) -> date | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _max_optional_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
