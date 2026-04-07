"""Database session management."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@dataclass(slots=True)
class DatabaseRuntime:
    """Database runtime objects created from settings."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def create_engine(database_url: str, *, use_null_pool: bool = False) -> AsyncEngine:
    """Create the async SQLAlchemy engine."""
    engine_kwargs: dict[str, object] = {"future": True}
    if use_null_pool:
        engine_kwargs["poolclass"] = NullPool
    return create_async_engine(database_url, **engine_kwargs)


def create_session_factory(database_url: str, *, use_null_pool: bool = False) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to the configured engine."""
    return create_database_runtime(database_url, use_null_pool=use_null_pool).session_factory


def create_database_runtime(database_url: str, *, use_null_pool: bool = False) -> DatabaseRuntime:
    """Create the engine and session factory together."""
    engine = create_engine(database_url, use_null_pool=use_null_pool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return DatabaseRuntime(engine=engine, session_factory=session_factory)
