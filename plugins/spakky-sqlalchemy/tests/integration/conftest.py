"""Integration test fixtures for spakky-sqlalchemy plugin."""

import logging
import os
from logging import Formatter, StreamHandler, getLogger
from typing import Any, AsyncGenerator, Generator

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
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)
from tests import apps
from tests.apps.orm import CommentTable, PostTable, UserTable

# Ensure all tables are registered for metadata creation
_ = (UserTable, PostTable, CommentTable)


@pytest.fixture(name="postgres_container", scope="package")
def postgres_container_fixture() -> Generator[PostgresContainer, Any, None]:
    """Start PostgreSQL container for integration tests.

    Yields:
        Running PostgreSQL container instance.
    """
    container = PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="testdb",
    ).with_bind_ports(5432, 5432)

    with container:
        yield container


@pytest.fixture(name="database_url", scope="package")
def database_url_fixture(postgres_container: PostgresContainer) -> str:
    """Get async database URL from PostgreSQL container.

    Args:
        postgres_container: Running PostgreSQL container.

    Returns:
        Async SQLAlchemy database URL.
    """
    # Get the connection URL and convert to async format for psycopg3
    sync_url = postgres_container.get_connection_url()
    # Handle both postgresql:// and postgresql+psycopg2:// formats
    async_url = sync_url.replace("psycopg2", "psycopg").replace(
        "postgresql://", "postgresql+psycopg://"
    )
    return async_url


@pytest.fixture(name="setup_env_vars", scope="package")
def setup_env_vars_fixture(database_url: str) -> str:
    """Set environment variables for SQLAlchemyConnectionConfig.

    Must run before app fixture to ensure config is properly loaded.

    Args:
        database_url: Async database connection URL.

    Returns:
        The database URL.
    """
    os.environ["SPAKKY_SQLALCHEMY__CONNECTION_STRING"] = database_url
    os.environ["SPAKKY_SQLALCHEMY__ECHO"] = "false"
    os.environ["SPAKKY_SQLALCHEMY__AUTOCOMMIT"] = "true"
    return database_url


@pytest.fixture(name="engine", scope="package")
def engine_fixture(database_url: str) -> Generator[AsyncEngine, Any, None]:
    """Create async SQLAlchemy engine.

    Args:
        database_url: Async database connection URL.

    Yields:
        Async SQLAlchemy engine.
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
    """Create async session factory.

    Args:
        engine: Async SQLAlchemy engine.

    Returns:
        Async session factory.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.fixture(name="app", scope="package")
def app_fixture(setup_env_vars: str) -> Generator[SpakkyApplication, Any, None]:
    """Create SpakkyApplication with SQLAlchemy plugin.

    Args:
        setup_env_vars: Database URL (ensures env vars are set before app creation).

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


@pytest.fixture(name="setup_database", scope="package", autouse=True)
async def setup_database_fixture(
    engine: AsyncEngine,
    app: SpakkyApplication,
) -> AsyncGenerator[None, Any]:
    """Create all tables from SchemaRegistry before tests and drop after.

    Args:
        engine: Async SQLAlchemy engine.
        app: SpakkyApplication instance (ensures Container is initialized).

    Yields:
        None after tables are created.
    """
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    metadata = schema_registry.metadata

    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)

    await engine.dispose()


@pytest.fixture(name="session", scope="function")
async def session_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, Any]:
    """Create async session for each test.

    Args:
        session_factory: Async session factory.

    Yields:
        Async SQLAlchemy session.
    """
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(name="async_session_manager", scope="function")
def async_session_manager_fixture(
    app: SpakkyApplication,
) -> AsyncSessionManager:
    """Get AsyncSessionManager from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncSessionManager instance.
    """
    return app.container.get(type_=AsyncSessionManager)


@pytest.fixture(name="async_transaction", scope="function")
def async_transaction_fixture(
    app: SpakkyApplication,
) -> AsyncTransaction:
    """Get AsyncTransaction from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncTransaction instance.
    """
    return app.container.get(type_=AsyncTransaction)


@pytest.fixture(name="session_manager", scope="function")
def session_manager_fixture(
    app: SpakkyApplication,
) -> SessionManager:
    """Get SessionManager from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        SessionManager instance.
    """
    return app.container.get(type_=SessionManager)


@pytest.fixture(name="transaction", scope="function")
def transaction_fixture(
    app: SpakkyApplication,
) -> Transaction:
    """Get Transaction from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        Transaction instance.
    """
    return app.container.get(type_=Transaction)
