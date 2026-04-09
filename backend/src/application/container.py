"""Composition root for backend services."""

from __future__ import annotations

from application.services import (
    AddWatchlistItemService,
    GetBatchSnapshotsService,
    GetCurrentUserService,
    GetMarketDataCapabilitiesService,
    GetWatchlistService,
    LoginUserService,
    RegisterUserService,
    RunSnapshotCoordinatorRefreshService,
    SearchTickersService,
    DeleteWatchlistItemService,
)
from domain.rules import build_market_data_mode
from infrastructure.cache import RedisSnapshotStore, create_redis_client
from infrastructure.db.session import create_database_runtime
from infrastructure.db.uow import SqlAlchemyUnitOfWorkFactory
from infrastructure.external import MassiveReferenceClient, MassiveSnapshotClient
from infrastructure.security import JwtService, PBKDF2PasswordHasher
from settings import Settings


class Container:
    """Own long-lived infrastructure dependencies and expose use-case services."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        database_runtime = create_database_runtime(
            settings.database_url,
            use_null_pool=settings.database_use_null_pool,
        )
        self._engine = database_runtime.engine
        self._session_factory = database_runtime.session_factory
        self._uow_factory = SqlAlchemyUnitOfWorkFactory(self._session_factory)
        self._password_hasher = PBKDF2PasswordHasher(
            iterations=settings.password_hash_iterations,
            salt_bytes=settings.password_hash_salt_bytes,
        )
        self._jwt_service = JwtService(
            secret_key=settings.app_secret_key,
            expires_in_seconds=settings.auth_access_token_ttl_seconds,
            algorithm=settings.auth_jwt_algorithm,
        )
        self._reference_client = MassiveReferenceClient(
            api_key=settings.massive_api_key,
            base_url=settings.massive_base_url,
            timeout_seconds=settings.massive_timeout_seconds,
        )
        self._snapshot_client = MassiveSnapshotClient(
            api_key=settings.massive_api_key,
            base_url=settings.massive_base_url,
            timeout_seconds=settings.massive_timeout_seconds,
        )
        self._redis = create_redis_client(settings.redis_url)
        self._snapshot_store = RedisSnapshotStore(
            self._redis,
            ttl_seconds=settings.resolved_market_data_snapshot_ttl_seconds,
        )
        self._market_data_mode = build_market_data_mode(
            delay_minutes=settings.market_data_delay_minutes,
            supports_stream=settings.market_data_supports_stream,
        )
        self._register_user_service = RegisterUserService(
            uow_factory=self._uow_factory,
            password_hasher=self._password_hasher,
            jwt_service=self._jwt_service,
        )
        self._login_user_service = LoginUserService(
            uow_factory=self._uow_factory,
            password_hasher=self._password_hasher,
            jwt_service=self._jwt_service,
        )
        self._current_user_service = GetCurrentUserService(
            uow_factory=self._uow_factory,
            jwt_service=self._jwt_service,
        )
        self._get_watchlist_service = GetWatchlistService(uow_factory=self._uow_factory)
        self._add_watchlist_item_service = AddWatchlistItemService(
            uow_factory=self._uow_factory,
            reference_client=self._reference_client,
        )
        self._delete_watchlist_item_service = DeleteWatchlistItemService(uow_factory=self._uow_factory)
        self._search_tickers_service = SearchTickersService(
            ticker_search_client=self._reference_client
        )
        self._get_market_data_capabilities_service = GetMarketDataCapabilitiesService(
            mode=self._market_data_mode,
        )
        self._get_batch_snapshots_service = GetBatchSnapshotsService(
            snapshot_store=self._snapshot_store,
            snapshot_client=self._snapshot_client,
            mode=self._market_data_mode,
            request_limit=settings.market_data_snapshot_request_limit,
            batch_size=settings.market_data_snapshot_batch_size,
        )
        self._run_snapshot_coordinator_refresh_service = RunSnapshotCoordinatorRefreshService(
            uow_factory=self._uow_factory,
            snapshot_store=self._snapshot_store,
            snapshot_client=self._snapshot_client,
            mode=self._market_data_mode,
            batch_size=settings.market_data_snapshot_batch_size,
            refresh_lock_ttl_seconds=settings.resolved_market_data_snapshot_refresh_lock_ttl_seconds,
        )

    def get_register_user_service(self) -> RegisterUserService:
        return self._register_user_service

    def get_login_user_service(self) -> LoginUserService:
        return self._login_user_service

    def get_current_user_service(self) -> GetCurrentUserService:
        return self._current_user_service

    def get_watchlist_service(self) -> GetWatchlistService:
        return self._get_watchlist_service

    def get_add_watchlist_item_service(self) -> AddWatchlistItemService:
        return self._add_watchlist_item_service

    def get_delete_watchlist_item_service(self) -> DeleteWatchlistItemService:
        return self._delete_watchlist_item_service

    def get_search_tickers_service(self) -> SearchTickersService:
        return self._search_tickers_service

    def get_market_data_capabilities_service(self) -> GetMarketDataCapabilitiesService:
        return self._get_market_data_capabilities_service

    def get_batch_snapshots_service(self) -> GetBatchSnapshotsService:
        return self._get_batch_snapshots_service

    def get_run_snapshot_coordinator_refresh_service(self) -> RunSnapshotCoordinatorRefreshService:
        return self._run_snapshot_coordinator_refresh_service

    async def shutdown(self) -> None:
        """Dispose long-lived infra dependencies."""
        await self._reference_client.close()
        await self._snapshot_client.close()
        await self._redis.aclose()
        await self._engine.dispose()
