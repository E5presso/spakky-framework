"""Pytest fixtures for SQLAlchemy integration tests."""

import logging
from collections.abc import AsyncGenerator, Generator
from logging import Formatter, StreamHandler, getLogger
from typing import Any

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.aspects import AsyncLoggingAspect, LoggingAspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

import spakky.plugins.sqlalchemy
from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from tests import apps


@pytest.fixture(name="postgres_container", scope="package")
def postgres_container_fixture() -> Generator[PostgresContainer, Any, None]:
    """Create a PostgreSQL container for integration tests.

    Yields:
        PostgresContainer instance.
    """
    container = PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="test_db",
    )
    with container:
        yield container


@pytest.fixture(name="database_url", scope="package")
def database_url_fixture(postgres_container: PostgresContainer) -> str:
    """Get the async database URL from the container.

    Args:
        postgres_container: PostgreSQL container.

    Returns:
        Async database URL for SQLAlchemy.
    """
    sync_url = postgres_container.get_connection_url()
    # Use psycopg driver for async (psycopg3 supports both sync and async)
    return sync_url.replace("postgresql://", "postgresql+psycopg://").replace(
        "postgresql+psycopg2://", "postgresql+psycopg://"
    )


@pytest.fixture(name="engine", scope="package")
def engine_fixture(database_url: str) -> Generator[AsyncEngine, Any, None]:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: Async database URL.

    Yields:
        AsyncEngine instance.
    """
    engine = create_async_engine(
        database_url,
        echo=True,
        pool_pre_ping=True,
    )
    yield engine


@pytest.fixture(name="session_factory", scope="package")
def session_factory_fixture(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory.

    Args:
        engine: AsyncEngine instance.

    Returns:
        Async session factory.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(name="app", scope="function")
def app_fixture() -> Generator[SpakkyApplication, Any, None]:
    """Create and configure the Spakky application.

    Yields:
        Configured SpakkyApplication instance.
    """
    logger = getLogger("debug")
    logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    logger.addHandler(console)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(include={spakky.plugins.sqlalchemy.PLUGIN_NAME})
        .add(AsyncLoggingAspect)
        .add(LoggingAspect)
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()
    logger.removeHandler(console)


@pytest.fixture(name="registry", scope="function")
def registry_fixture(app: SpakkyApplication) -> Generator[ModelRegistry, Any, None]:
    """Get the ModelRegistry from the application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        ModelRegistry instance.
    """
    registry = app.container.get(ModelRegistry)

    yield registry

    registry.sqlalchemy_registry.dispose()


@pytest.fixture(name="create_tables", scope="function")
async def create_tables_fixture(
    engine: AsyncEngine,
    registry: ModelRegistry,
) -> AsyncGenerator[None, None]:
    """Create database tables from registered models.

    This fixture creates tables before the test and drops them after.

    Args:
        engine: AsyncEngine instance.
        registry: ModelRegistry with registered models.

    Yields:
        None after tables are created.
    """
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(registry.metadata.create_all)

    yield

    # Drop all tables after test
    async with engine.begin() as conn:
        await conn.run_sync(registry.metadata.drop_all)

    # Dispose connection pool to clear cached type OIDs (for PostgreSQL ENUM)
    await engine.dispose()


@pytest.fixture(name="session", scope="function")
async def session_fixture(
    session_factory: async_sessionmaker[AsyncSession],
    create_tables: None,
) -> AsyncGenerator[AsyncSession, None]:
    """Create an async session for testing.

    Args:
        session_factory: Async session factory.
        create_tables: Fixture that creates tables.

    Yields:
        AsyncSession instance.
    """
    async with session_factory() as session:
        yield session
        await session.rollback()
