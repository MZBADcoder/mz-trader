"""Integration tests for terminal snapshot repository behavior."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from domain.entities import Snapshot
from infrastructure.repositories.market_terminal_snapshot_repository import MarketTerminalSnapshotRepository


def _snapshot(ticker: str, *, last: float, data_source: str) -> Snapshot:
    return Snapshot(
        ticker=ticker,
        last=last,
        regular_close=212.00,
        change=1.23,
        change_pct=0.58,
        open=211.10,
        high=213.00,
        low=210.60,
        volume=45678901,
        prev_close=211.11,
        market_status="closed",
        session="closed",
        trading_day=date(2026, 4, 8),
        last_session="after_hours",
        last_trade_at=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
        delay_minutes=15,
        is_realtime=False,
        provider_updated_at=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 9, 0, 30, tzinfo=UTC),
        data_source=data_source,
    )


def test_market_terminal_snapshot_repository_upsert_updates_existing_row(session_factory) -> None:
    async def exercise_repository() -> None:
        async with session_factory() as session:
            repository = MarketTerminalSnapshotRepository(session)
            await repository.upsert_many(
                snapshots=[_snapshot("AAPL", last=100.0, data_source="first")],
                captured_at=datetime(2026, 4, 9, 0, 30, tzinfo=UTC),
            )
            await session.commit()

        async with session_factory() as session:
            repository = MarketTerminalSnapshotRepository(session)
            await repository.upsert_many(
                snapshots=[_snapshot("AAPL", last=101.0, data_source="second")],
                captured_at=datetime(2026, 4, 9, 0, 45, tzinfo=UTC),
            )
            await session.commit()

        async with session_factory() as session:
            repository = MarketTerminalSnapshotRepository(session)
            loaded = await repository.list_for_tickers(
                tickers=["AAPL"],
                trading_day=date(2026, 4, 8),
            )

        assert len(loaded) == 1
        assert loaded[0].last == 101.0
        assert loaded[0].data_source == "second"

    asyncio.run(exercise_repository())
