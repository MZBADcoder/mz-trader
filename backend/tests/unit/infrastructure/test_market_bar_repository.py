"""Market bar repository tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities import CanonicalBar
from infrastructure.repositories.market_bar_repository import (
    MARKET_BAR_UPSERT_BATCH_SIZE,
    MarketBarRepository,
)


class FakeSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def _bar(index: int, *, granularity: str) -> CanonicalBar:
    bucket_start_at = datetime(2026, 4, 15, 13, 30, tzinfo=UTC) + timedelta(minutes=index)
    return CanonicalBar(
        ticker="AAPL",
        adjustment="split_adjusted",
        granularity=granularity,
        bucket_start_at=bucket_start_at,
        trading_day=date(2026, 4, 15),
        session_kind="regular",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000,
        vw=100.4,
        trade_count=10,
        provider_updated_at=bucket_start_at,
        is_final=True,
        first_synced_at=bucket_start_at,
        last_synced_at=bucket_start_at,
    )


def test_upsert_1m_splits_large_batches() -> None:
    session = FakeSession()
    repository = MarketBarRepository(cast(AsyncSession, session))
    bars = [_bar(index, granularity="1m") for index in range(MARKET_BAR_UPSERT_BATCH_SIZE + 1)]

    asyncio.run(repository.upsert_1m(bars))

    assert len(session.statements) == 2


def test_upsert_1d_splits_large_batches() -> None:
    session = FakeSession()
    repository = MarketBarRepository(cast(AsyncSession, session))
    bars = [_bar(index, granularity="1d") for index in range(MARKET_BAR_UPSERT_BATCH_SIZE + 1)]

    asyncio.run(repository.upsert_1d(bars))

    assert len(session.statements) == 2
