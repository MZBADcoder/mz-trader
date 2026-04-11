"""Redis-backed snapshot cache."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from domain.entities import Snapshot
from domain.exceptions import InternalError


class RedisSnapshotStore:
    """Persist normalized snapshots in Redis."""

    _SNAPSHOT_COORDINATOR_LOCK_KEY = "snapshot:coordinator:refresh_lock"

    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    async def get_many(self, tickers: list[str]) -> dict[str, Snapshot]:
        """Return cached snapshots keyed by ticker."""
        if not tickers:
            return {}

        values = await self._redis.mget([self._build_key(ticker) for ticker in tickers])
        snapshots: dict[str, Snapshot] = {}
        for ticker, raw_value in zip(tickers, values, strict=False):
            if raw_value is None:
                continue
            snapshots[ticker] = self._deserialize_snapshot(raw_value)
        return snapshots

    async def set_many(self, snapshots: list[Snapshot]) -> None:
        """Write snapshots back to Redis with TTL."""
        if not snapshots:
            return

        async with self._redis.pipeline(transaction=False) as pipeline:
            for snapshot in snapshots:
                pipeline.set(
                    self._build_key(snapshot.ticker),
                    self._serialize_snapshot(snapshot),
                    ex=self._ttl_seconds,
                )
            await pipeline.execute()

    async def acquire_refresh_lock(self, *, ttl_seconds: int) -> str | None:
        """Acquire the snapshot coordinator lock when no refresh is active."""
        token = uuid.uuid4().hex
        acquired = await self._redis.set(
            self._SNAPSHOT_COORDINATOR_LOCK_KEY,
            token,
            ex=ttl_seconds,
            nx=True,
        )
        if not acquired:
            return None
        return token

    async def release_refresh_lock(self, token: str) -> bool:
        """Release the snapshot coordinator lock when owned by this worker."""
        released = await self._redis.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            end
            return 0
            """,
            1,
            self._SNAPSHOT_COORDINATOR_LOCK_KEY,
            token,
        )
        return bool(released)

    def _build_key(self, ticker: str) -> str:
        return f"snapshot:{ticker}"

    def _serialize_snapshot(self, snapshot: Snapshot) -> str:
        payload = {
            "ticker": snapshot.ticker,
            "last": snapshot.last,
            "change": snapshot.change,
            "change_pct": snapshot.change_pct,
            "open": snapshot.open,
            "high": snapshot.high,
            "low": snapshot.low,
            "volume": snapshot.volume,
            "prev_close": snapshot.prev_close,
            "market_status": snapshot.market_status,
            "delay_minutes": snapshot.delay_minutes,
            "is_realtime": snapshot.is_realtime,
            "provider_updated_at": snapshot.provider_updated_at.astimezone(UTC).isoformat(),
            "fetched_at": snapshot.fetched_at.astimezone(UTC).isoformat(),
            "data_source": snapshot.data_source,
        }
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    def _deserialize_snapshot(self, raw_value: str) -> Snapshot:
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise InternalError(detail="Cached snapshot payload is invalid.") from exc

        if not isinstance(payload, dict):
            raise InternalError(detail="Cached snapshot payload is invalid.")

        try:
            return Snapshot(
                ticker=str(payload["ticker"]),
                last=float(payload["last"]),
                change=float(payload["change"]),
                change_pct=float(payload["change_pct"]),
                open=float(payload["open"]),
                high=float(payload["high"]),
                low=float(payload["low"]),
                volume=int(payload["volume"]),
                prev_close=float(payload["prev_close"]),
                market_status=str(payload["market_status"]),
                delay_minutes=int(payload["delay_minutes"]),
                is_realtime=bool(payload["is_realtime"]),
                provider_updated_at=self._parse_datetime(payload["provider_updated_at"]),
                fetched_at=self._parse_datetime(payload["fetched_at"]),
                data_source=str(payload.get("data_source", "redis")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InternalError(detail="Cached snapshot payload is invalid.") from exc

    def _parse_datetime(self, raw_value: object) -> datetime:
        if not isinstance(raw_value, str):
            raise InternalError(detail="Cached snapshot payload is invalid.")
        normalized = raw_value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
