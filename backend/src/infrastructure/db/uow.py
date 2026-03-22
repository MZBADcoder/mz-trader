"""Async unit of work implementation."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.repositories.user_repository import UserRepository
from infrastructure.repositories.watchlist_repository import WatchlistRepository


class SqlAlchemyUnitOfWork:
    """Own a session and repositories for a single use case."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.users: UserRepository | None = None
        self.watchlist: WatchlistRepository | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self.users = UserRepository(self.session)
        self.watchlist = WatchlistRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.session is None:
            return
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()
        self.session = None
        self.users = None
        self.watchlist = None

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self.session is None:
            raise RuntimeError("Unit of work is not active.")
        await self.session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        if self.session is None:
            raise RuntimeError("Unit of work is not active.")
        await self.session.rollback()


class SqlAlchemyUnitOfWorkFactory:
    """Create unit of work instances on demand."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def build(self) -> SqlAlchemyUnitOfWork:
        """Create a new unit of work instance."""
        return SqlAlchemyUnitOfWork(self._session_factory)
