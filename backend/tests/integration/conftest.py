"""Integration test fixtures backed by a temporary PostgreSQL container."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import docker
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from docker.errors import DockerException
from redis import Redis
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from infrastructure.db.models import Base
from infrastructure.db.session import DatabaseRuntime, create_database_runtime
from main import create_app
from settings import Settings


def _to_asyncpg_url(connection_url: str) -> str:
    """Convert a testcontainers connection URL to the asyncpg dialect."""
    if connection_url.startswith("postgresql+"):
        scheme, remainder = connection_url.split("://", maxsplit=1)
        _, _, driver = scheme.partition("+")
        if driver == "asyncpg":
            return connection_url
        return f"postgresql+asyncpg://{remainder}"

    if connection_url.startswith("postgresql://"):
        return connection_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    raise ValueError(f"Unsupported PostgreSQL connection URL: {connection_url}")


async def _reset_database(runtime: DatabaseRuntime) -> None:
    """Recreate every ORM-managed table for a clean test database."""
    async with runtime.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


def _ensure_docker_available() -> None:
    """Skip integration tests when the local Docker daemon is unavailable."""
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        pytest.skip(f"Docker daemon is required for integration tests: {exc}")
    else:
        client.close()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start a dedicated PostgreSQL container for integration tests."""
    _ensure_docker_available()
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="trader_refactor_test",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Return an async SQLAlchemy connection URL for the test database."""
    return _to_asyncpg_url(postgres_container.get_connection_url())


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """Start a dedicated Redis container for integration tests."""
    _ensure_docker_available()
    with RedisContainer(image="redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    """Return a Redis URL for integration tests."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def database_runtime(database_url: str) -> Iterator[DatabaseRuntime]:
    """Create a reusable engine and session factory for the test session."""
    runtime = create_database_runtime(database_url, use_null_pool=True)
    yield runtime
    asyncio.run(runtime.engine.dispose())


@pytest.fixture(scope="session")
def integration_settings(
    database_url: str,
    redis_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Settings:
    """Build dedicated app settings for integration tests."""
    base_settings = Settings()
    return Settings(
        app_env="test",
        app_secret_key="integration-test-secret",
        auth_access_token_ttl_seconds=3600,
        password_hash_iterations=1_000,
        database_url=database_url,
        database_use_null_pool=True,
        redis_url=redis_url,
        celery_broker_url=redis_url,
        celery_result_backend=redis_url,
        massive_api_key=base_settings.massive_api_key,
        massive_base_url=base_settings.massive_base_url,
        massive_timeout_seconds=base_settings.massive_timeout_seconds,
        market_data_delay_minutes=base_settings.market_data_delay_minutes,
        market_data_supports_stream=base_settings.market_data_supports_stream,
        market_data_snapshot_request_limit=base_settings.market_data_snapshot_request_limit,
        market_data_snapshot_batch_size=base_settings.market_data_snapshot_batch_size,
        market_data_snapshot_refresh_interval_seconds=base_settings.market_data_snapshot_refresh_interval_seconds,
        market_data_snapshot_ttl_seconds=base_settings.market_data_snapshot_ttl_seconds,
        market_data_bars_current_day_refresh_interval_seconds=base_settings.market_data_bars_current_day_refresh_interval_seconds,
        market_data_bars_post_close_finalizer_hour_et=base_settings.market_data_bars_post_close_finalizer_hour_et,
        market_data_bars_post_close_finalizer_minute_et=base_settings.market_data_bars_post_close_finalizer_minute_et,
        log_dir=tmp_path_factory.mktemp("integration-logs"),
        log_file_name="integration.log",
        log_to_stdout=False,
    )


@pytest.fixture(autouse=True)
def reset_database_schema(database_runtime: DatabaseRuntime) -> Iterator[None]:
    """Reset the schema before each test to keep cases isolated."""
    asyncio.run(_reset_database(database_runtime))
    yield


@pytest.fixture(scope="session")
def redis_client(redis_url: str) -> Iterator[Redis]:
    """Expose a reusable Redis client to integration tests."""
    client = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
    yield client
    client.close()


@pytest.fixture(autouse=True)
def reset_redis(redis_client: Redis) -> Iterator[None]:
    """Clear Redis state before each test to keep cases isolated."""
    redis_client.flushdb()
    yield


@pytest.fixture
def session_factory(database_runtime: DatabaseRuntime):
    """Expose the async session factory to integration tests."""
    return database_runtime.session_factory


@pytest.fixture
def app(integration_settings: Settings) -> FastAPI:
    """Create a FastAPI app wired to the integration dependencies."""
    return create_app(integration_settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Create a FastAPI test client wired to the real PostgreSQL database."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def container(app: FastAPI):
    """Expose the real application container used by integration tests."""
    return app.state.container
