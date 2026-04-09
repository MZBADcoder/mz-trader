"""Redis runtime helpers."""

from __future__ import annotations

from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis:
    """Create a shared async Redis client."""
    return Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
