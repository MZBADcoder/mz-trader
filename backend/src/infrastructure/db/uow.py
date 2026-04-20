"""Async unit of work implementation."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.repositories.market_bar_repository import MarketBarRepository
from infrastructure.repositories.market_ticker_bars_state_repository import MarketTickerBarsStateRepository
from infrastructure.repositories.user_repository import UserRepository
from infrastructure.repositories.watchlist_repository import WatchlistRepository


class SqlAlchemyUnitOfWork:
    """Own a session and repositories for a single use case."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._bars: MarketBarRepository | None = None
        self._ticker_bars_state: MarketTickerBarsStateRepository | None = None
        self._users: UserRepository | None = None
        self._watchlist: WatchlistRepository | None = None

    @property
    def session(self) -> AsyncSession:
        """Return the active session."""
        if self._session is None:
            raise RuntimeError("Unit of work is not active.")
        return self._session

    @property
    def users(self) -> UserRepository:
        """Return the active user repository."""
        if self._users is None:
            raise RuntimeError("User repository is not available in the active unit of work.")
        return self._users

    @property
    def bars(self) -> MarketBarRepository:
        """Return the active market bar repository."""
        if self._bars is None:
            raise RuntimeError("Market bar repository is not available in the active unit of work.")
        return self._bars

    @property
    def watchlist(self) -> WatchlistRepository:
        """Return the active watchlist repository."""
        if self._watchlist is None:
            raise RuntimeError("Watchlist repository is not available in the active unit of work.")
        return self._watchlist

    @property
    def ticker_bars_state(self) -> MarketTickerBarsStateRepository:
        """Return the active ticker bars state repository."""
        if self._ticker_bars_state is None:
            raise RuntimeError("Ticker bars state repository is not available in the active unit of work.")
        return self._ticker_bars_state

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        session = self._session_factory()
        self._session = session
        self._bars = MarketBarRepository(session)
        self._ticker_bars_state = MarketTickerBarsStateRepository(session)
        self._users = UserRepository(session)
        self._watchlist = WatchlistRepository(session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()
        self._session = None
        self._bars = None
        self._ticker_bars_state = None
        self._users = None
        self._watchlist = None

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        await self.session.rollback()


class SqlAlchemyUnitOfWorkFactory:
    """Create unit of work instances on demand."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def build(self) -> SqlAlchemyUnitOfWork:
        """Create a new unit of work instance."""
        return SqlAlchemyUnitOfWork(self._session_factory)
