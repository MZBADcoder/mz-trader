"""Ticker bars readiness repository implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import TickerBarsState
from infrastructure.db.mappers import to_market_ticker_bars_state_entity
from infrastructure.db.models import MarketTickerBarsStateModel


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class MarketTickerBarsStateRepository:
    """Persist and query ticker-level bars state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, ticker: str) -> TickerBarsState | None:
        model = await self._session.get(MarketTickerBarsStateModel, ticker)
        return to_market_ticker_bars_state_entity(model) if model is not None else None

    async def get_for_update(self, *, ticker: str) -> TickerBarsState | None:
        stmt: Select[tuple[MarketTickerBarsStateModel]] = (
            select(MarketTickerBarsStateModel)
            .where(MarketTickerBarsStateModel.ticker == ticker)
            .with_for_update()
        )
        model = await self._session.scalar(stmt)
        return to_market_ticker_bars_state_entity(model) if model is not None else None

    async def list_for_tickers(self, *, tickers: list[str]) -> list[TickerBarsState]:
        if not tickers:
            return []
        stmt: Select[tuple[MarketTickerBarsStateModel]] = (
            select(MarketTickerBarsStateModel)
            .where(MarketTickerBarsStateModel.ticker.in_(tickers))
            .order_by(MarketTickerBarsStateModel.ticker.asc())
        )
        result = await self._session.scalars(stmt)
        return [to_market_ticker_bars_state_entity(model) for model in result.all()]

    async def list_by_statuses(self, *, statuses: list[str]) -> list[TickerBarsState]:
        if not statuses:
            return []
        stmt: Select[tuple[MarketTickerBarsStateModel]] = (
            select(MarketTickerBarsStateModel)
            .where(MarketTickerBarsStateModel.status.in_(statuses))
            .order_by(MarketTickerBarsStateModel.ticker.asc())
        )
        result = await self._session.scalars(stmt)
        return [to_market_ticker_bars_state_entity(model) for model in result.all()]

    async def upsert(self, state: TickerBarsState) -> None:
        stmt = insert(MarketTickerBarsStateModel).values(
            {
                "ticker": state.ticker,
                "status": state.status,
                "bootstrap_requested_at": _ensure_utc(state.bootstrap_requested_at) if state.bootstrap_requested_at is not None else None,
                "bootstrap_started_at": _ensure_utc(state.bootstrap_started_at) if state.bootstrap_started_at is not None else None,
                "bootstrap_finished_at": _ensure_utc(state.bootstrap_finished_at) if state.bootstrap_finished_at is not None else None,
                "bootstrap_failed_at": _ensure_utc(state.bootstrap_failed_at) if state.bootstrap_failed_at is not None else None,
                "last_reconciled_at": _ensure_utc(state.last_reconciled_at) if state.last_reconciled_at is not None else None,
                "earliest_1m_trading_day": state.earliest_1m_trading_day,
                "last_1m_trading_day": state.last_1m_trading_day,
                "last_1m_bucket_start_at": _ensure_utc(state.last_1m_bucket_start_at) if state.last_1m_bucket_start_at is not None else None,
                "earliest_1d_trading_day": state.earliest_1d_trading_day,
                "latest_1d_trading_day": state.latest_1d_trading_day,
                "last_error_code": state.last_error_code,
                "last_error_message": state.last_error_message,
                "created_at": _ensure_utc(state.created_at),
                "updated_at": _ensure_utc(state.updated_at),
            }
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "status": stmt.excluded.status,
                "bootstrap_requested_at": stmt.excluded.bootstrap_requested_at,
                "bootstrap_started_at": stmt.excluded.bootstrap_started_at,
                "bootstrap_finished_at": stmt.excluded.bootstrap_finished_at,
                "bootstrap_failed_at": stmt.excluded.bootstrap_failed_at,
                "last_reconciled_at": stmt.excluded.last_reconciled_at,
                "earliest_1m_trading_day": stmt.excluded.earliest_1m_trading_day,
                "last_1m_trading_day": stmt.excluded.last_1m_trading_day,
                "last_1m_bucket_start_at": stmt.excluded.last_1m_bucket_start_at,
                "earliest_1d_trading_day": stmt.excluded.earliest_1d_trading_day,
                "latest_1d_trading_day": stmt.excluded.latest_1d_trading_day,
                "last_error_code": stmt.excluded.last_error_code,
                "last_error_message": stmt.excluded.last_error_message,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)

    async def ensure_pending(self, *, ticker: str, requested_at: datetime) -> None:
        existing = await self.get_for_update(ticker=ticker)
        if existing is not None:
            if existing.status == "ready":
                return
            pending = TickerBarsState(
                ticker=ticker,
                status="pending",
                bootstrap_requested_at=requested_at,
                bootstrap_started_at=existing.bootstrap_started_at,
                bootstrap_finished_at=existing.bootstrap_finished_at,
                bootstrap_failed_at=existing.bootstrap_failed_at,
                last_reconciled_at=existing.last_reconciled_at,
                earliest_1m_trading_day=existing.earliest_1m_trading_day,
                last_1m_trading_day=existing.last_1m_trading_day,
                last_1m_bucket_start_at=existing.last_1m_bucket_start_at,
                earliest_1d_trading_day=existing.earliest_1d_trading_day,
                latest_1d_trading_day=existing.latest_1d_trading_day,
                last_error_code=existing.last_error_code,
                last_error_message=existing.last_error_message,
                created_at=existing.created_at,
                updated_at=requested_at,
            )
            await self.upsert(pending)
            return

        pending = TickerBarsState(
            ticker=ticker,
            status="pending",
            bootstrap_requested_at=requested_at,
            bootstrap_started_at=None,
            bootstrap_finished_at=None,
            bootstrap_failed_at=None,
            last_reconciled_at=None,
            earliest_1m_trading_day=None,
            last_1m_trading_day=None,
            last_1m_bucket_start_at=None,
            earliest_1d_trading_day=None,
            latest_1d_trading_day=None,
            last_error_code=None,
            last_error_message=None,
            created_at=requested_at,
            updated_at=requested_at,
        )
        await self.upsert(pending)

    async def mark_failed(self, *, ticker: str, failed_at: datetime, error_message: str) -> None:
        existing = await self.get_for_update(ticker=ticker)
        if existing is None:
            await self.ensure_pending(ticker=ticker, requested_at=failed_at)
            existing = await self.get_for_update(ticker=ticker)
            assert existing is not None
        if self._has_newer_ready_success(existing=existing, at=failed_at):
            return
        failed = TickerBarsState(
            ticker=ticker,
            status="failed",
            bootstrap_requested_at=existing.bootstrap_requested_at,
            bootstrap_started_at=existing.bootstrap_started_at,
            bootstrap_finished_at=existing.bootstrap_finished_at,
            bootstrap_failed_at=failed_at,
            last_reconciled_at=existing.last_reconciled_at,
            earliest_1m_trading_day=existing.earliest_1m_trading_day,
            last_1m_trading_day=existing.last_1m_trading_day,
            last_1m_bucket_start_at=existing.last_1m_bucket_start_at,
            earliest_1d_trading_day=existing.earliest_1d_trading_day,
            latest_1d_trading_day=existing.latest_1d_trading_day,
            last_error_code="bootstrap_failed",
            last_error_message=error_message,
            created_at=existing.created_at,
            updated_at=failed_at,
        )
        await self.upsert(failed)

    async def mark_degraded(self, *, ticker: str, degraded_at: datetime, error_message: str) -> None:
        existing = await self.get_for_update(ticker=ticker)
        if existing is None:
            await self.ensure_pending(ticker=ticker, requested_at=degraded_at)
            existing = await self.get_for_update(ticker=ticker)
            assert existing is not None
        if self._has_newer_ready_success(existing=existing, at=degraded_at):
            return
        degraded = TickerBarsState(
            ticker=ticker,
            status="degraded",
            bootstrap_requested_at=existing.bootstrap_requested_at,
            bootstrap_started_at=existing.bootstrap_started_at,
            bootstrap_finished_at=existing.bootstrap_finished_at,
            bootstrap_failed_at=existing.bootstrap_failed_at,
            last_reconciled_at=existing.last_reconciled_at,
            earliest_1m_trading_day=existing.earliest_1m_trading_day,
            last_1m_trading_day=existing.last_1m_trading_day,
            last_1m_bucket_start_at=existing.last_1m_bucket_start_at,
            earliest_1d_trading_day=existing.earliest_1d_trading_day,
            latest_1d_trading_day=existing.latest_1d_trading_day,
            last_error_code="degraded",
            last_error_message=error_message,
            created_at=existing.created_at,
            updated_at=degraded_at,
        )
        await self.upsert(degraded)

    def _has_newer_ready_success(self, *, existing: TickerBarsState, at: datetime) -> bool:
        if existing.status != "ready":
            return False
        success_at = max(
            value
            for value in (
                existing.bootstrap_finished_at,
                existing.last_reconciled_at,
                existing.updated_at,
            )
            if value is not None
        )
        return success_at >= _ensure_utc(at)
