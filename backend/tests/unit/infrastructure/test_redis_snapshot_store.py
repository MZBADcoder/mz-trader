"""Redis snapshot store tests."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime

from domain.entities import Snapshot
from infrastructure.cache.redis_snapshot_store import RedisSnapshotStore


def _snapshot(ticker: str) -> Snapshot:
    return Snapshot(
        ticker=ticker,
        last=212.34,
        regular_close=212.00,
        change=1.23,
        change_pct=0.58,
        open=211.10,
        high=213.00,
        low=210.60,
        volume=45678901,
        prev_close=211.11,
        market_status="regular",
        session="regular",
        trading_day=date(2026, 4, 8),
        last_session="regular",
        last_trade_at=datetime(2026, 4, 8, 14, 30, tzinfo=UTC),
        delay_minutes=15,
        is_realtime=False,
        provider_updated_at=datetime(2026, 4, 8, 8, 30, tzinfo=UTC),
        fetched_at=datetime(2026, 4, 8, 8, 31, tzinfo=UTC),
        data_source="massive_fallback",
    )


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._commands: list[tuple[str, str, int]] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def set(self, key: str, value: str, *, ex: int) -> None:
        self._commands.append((key, value, ex))

    async def execute(self) -> None:
        for key, value, ex in self._commands:
            self._redis.values[key] = value
            self._redis.expirations[key] = ex


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.values.get(key) for key in keys]

    def pipeline(self, *, transaction: bool) -> FakePipeline:
        assert transaction is False
        return FakePipeline(self)

    async def set(self, key: str, value: str, *, ex: int, nx: bool) -> bool | None:
        if nx and key in self.values:
            return None
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        assert numkeys == 1
        if self.values.get(key) != token:
            return 0
        del self.values[key]
        self.expirations.pop(key, None)
        return 1


def test_redis_snapshot_store_round_trips_snapshot_payload() -> None:
    redis = FakeRedis()
    store = RedisSnapshotStore(redis, ttl_seconds=50)

    asyncio.run(store.set_many([_snapshot("AAPL")]))
    result = asyncio.run(store.get_many(["AAPL", "MSFT"]))

    assert list(result) == ["AAPL"]
    assert result["AAPL"] == _snapshot("AAPL")
    assert redis.expirations["snapshot:AAPL"] == 50
    payload = json.loads(redis.values["snapshot:AAPL"])
    assert payload["regular_close"] == 212.0
    assert payload["session"] == "regular"
    assert payload["trading_day"] == "2026-04-08"
    assert payload["provider_updated_at"] == "2026-04-08T08:30:00+00:00"
    assert payload["fetched_at"] == "2026-04-08T08:31:00+00:00"


def test_redis_snapshot_store_lock_is_single_flight_and_owner_released() -> None:
    redis = FakeRedis()
    store = RedisSnapshotStore(redis, ttl_seconds=50)

    first_token = asyncio.run(store.acquire_refresh_lock(ttl_seconds=25))
    second_token = asyncio.run(store.acquire_refresh_lock(ttl_seconds=25))
    released_with_wrong_token = asyncio.run(store.release_refresh_lock("wrong-token"))
    released_with_owner_token = asyncio.run(store.release_refresh_lock(first_token or ""))
    third_token = asyncio.run(store.acquire_refresh_lock(ttl_seconds=25))

    assert first_token is not None
    assert second_token is None
    assert released_with_wrong_token is False
    assert released_with_owner_token is True
    assert third_token is not None
    assert redis.expirations["snapshot:coordinator:refresh_lock"] == 25
