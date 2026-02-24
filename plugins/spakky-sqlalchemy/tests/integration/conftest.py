"""Integration test fixtures for spakky-sqlalchemy plugin."""

import logging
import os
from logging import Formatter, StreamHandler, getLogger
from typing import Any, AsyncGenerator, Generator

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.aspects import AsyncLoggingAspect, LoggingAspect
from testcontainers.postgres import PostgresContainer

import spakky.plugins.sqlalchemy
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests import apps


@pytest.fixture(name="postgres_container", scope="session")
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
    )

    with container:
        yield container


@pytest.fixture(name="database_url", scope="session")
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


@pytest.fixture(name="setup_env_vars", scope="session")
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


@pytest.fixture(name="app", scope="session")
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


@pytest.fixture(name="schema_registry", scope="session")
def schema_registry_fixture(app: SpakkyApplication) -> SchemaRegistry:
    """Get SchemaRegistry from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        SchemaRegistry instance.
    """

    return app.container.get(type_=SchemaRegistry)


@pytest.fixture(name="async_connection_manager", scope="session")
def async_connection_manager_fixture(app: SpakkyApplication) -> AsyncConnectionManager:
    """Get AsyncConnectionManager from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncConnectionManager instance.
    """

    return app.container.get(type_=AsyncConnectionManager)


@pytest.fixture(name="setup_database", scope="session", autouse=True)
async def setup_database_fixture(
    schema_registry: SchemaRegistry,
    async_connection_manager: AsyncConnectionManager,
) -> AsyncGenerator[None, Any]:
    """Set up database schema for integration tests.

    Creates all tables before tests and drops them after.
    Engine disposal must happen here (same event loop as connection usage).

    Args:
        schema_registry: Schema registry containing table metadata.
        async_connection_manager: Async connection manager for database operations.

    Yields:
        None after database setup is complete.
    """

    metadata = schema_registry.metadata

    async with async_connection_manager.connection.begin() as conn:
        await conn.run_sync(metadata.create_all)

    yield

    async with async_connection_manager.connection.begin() as conn:
        await conn.run_sync(metadata.drop_all)

    await async_connection_manager.dispose()


@pytest.fixture(name="async_transaction", scope="function")
def async_transaction_fixture(app: SpakkyApplication) -> AsyncTransaction:
    """Get AsyncTransaction from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncTransaction instance.
    """
    return app.container.get(type_=AsyncTransaction)
