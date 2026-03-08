import logging
import os
from logging import Formatter, StreamHandler, getLogger
from typing import Any, AsyncGenerator, Generator

import pytest
import spakky.data
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.aspects import AsyncLoggingAspect, LoggingAspect
from testcontainers.postgres import PostgresContainer

import spakky.plugins.sqlalchemy
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction

import spakky.plugins.outbox
from spakky.plugins.outbox.persistency.table import OutboxBase

import tests.apps


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
    )
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
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("psycopg2", "psycopg").replace(
        "postgresql://", "postgresql+psycopg://"
    )
    return async_url


@pytest.fixture(name="setup_env_vars", scope="package")
def setup_env_vars_fixture(database_url: str) -> str:
    """Set environment variables for plugin configuration.

    Args:
        database_url: Async database connection URL.

    Returns:
        The database URL.
    """
    os.environ["SPAKKY_SQLALCHEMY__CONNECTION_STRING"] = database_url
    os.environ["SPAKKY_SQLALCHEMY__ECHO"] = "false"
    os.environ["SPAKKY_SQLALCHEMY__AUTOCOMMIT"] = "true"
    os.environ["SPAKKY_OUTBOX__AUTO_CREATE_TABLE"] = "true"
    return database_url


@pytest.fixture(name="app", scope="package")
def app_fixture(setup_env_vars: str) -> Generator[SpakkyApplication, Any, None]:
    """Create SpakkyApplication with SQLAlchemy + Outbox plugins.

    Args:
        setup_env_vars: Database URL (ensures env vars are set before app creation).

    Yields:
        Configured SpakkyApplication instance.
    """
    debug_logger = getLogger("debug")
    debug_logger.setLevel(logging.DEBUG)
    console = StreamHandler()
    console.setLevel(level=logging.DEBUG)
    console.setFormatter(Formatter("[%(levelname)s][%(asctime)s]: %(message)s"))
    debug_logger.addHandler(console)

    app = (
        SpakkyApplication(ApplicationContext())
        .load_plugins(
            include={
                spakky.plugins.sqlalchemy.PLUGIN_NAME,
                spakky.plugins.outbox.PLUGIN_NAME,
                spakky.data.PLUGIN_NAME,
                # NOTE: spakky.event.PLUGIN_NAME is intentionally omitted —
                # spakky-outbox provides all event infrastructure including its own bus.
            }
        )
        .add(AsyncLoggingAspect)
        .add(LoggingAspect)
        .scan(tests.apps)
    )
    app.start()

    yield app

    app.stop()
    debug_logger.removeHandler(console)


@pytest.fixture(name="async_connection_manager", scope="package")
def async_connection_manager_fixture(app: SpakkyApplication) -> AsyncConnectionManager:
    """Get AsyncConnectionManager from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncConnectionManager instance.
    """
    return app.container.get(type_=AsyncConnectionManager)


@pytest.fixture(name="setup_database", scope="package", autouse=True)
async def setup_database_fixture(
    async_connection_manager: AsyncConnectionManager,
) -> AsyncGenerator[None, Any]:
    """Drop the outbox table after all tests complete.

    The table is created by OutboxRelay.initialize_async() (auto_create_table=True)
    when the application starts, so no explicit CREATE is needed here.

    Args:
        async_connection_manager: Async connection manager.

    Yields:
        None after setup check is complete.
    """
    yield

    async with async_connection_manager.connection.begin() as conn:
        await conn.run_sync(OutboxBase.metadata.drop_all)

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
