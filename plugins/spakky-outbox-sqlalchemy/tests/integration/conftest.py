"""Integration test fixtures for spakky-outbox-sqlalchemy plugin."""

import os
from typing import Any, AsyncGenerator, Generator
from uuid import uuid4

import pytest
import spakky.plugins.sqlalchemy
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from spakky.plugins.sqlalchemy.persistency.transaction import (
    AsyncTransaction,
    Transaction,
)
from testcontainers.postgres import PostgresContainer

import spakky.plugins.outbox_sqlalchemy
from spakky.plugins.outbox_sqlalchemy.adapters.storage import (
    AsyncSqlAlchemyOutboxStorage,
    SqlAlchemyOutboxStorage,
)


@pytest.fixture(name="postgres_container", scope="package")
def postgres_container_fixture() -> Generator[PostgresContainer, Any, None]:
    """Start PostgreSQL container for integration tests."""
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
    """Get async database URL from PostgreSQL container."""
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("psycopg2", "psycopg").replace(
        "postgresql://", "postgresql+psycopg://"
    )
    return async_url


@pytest.fixture(name="setup_env_vars", scope="package")
def setup_env_vars_fixture(database_url: str) -> str:
    """Set environment variables for SQLAlchemyConnectionConfig."""
    os.environ["SPAKKY_SQLALCHEMY__CONNECTION_STRING"] = database_url
    os.environ["SPAKKY_SQLALCHEMY__ECHO"] = "false"
    os.environ["SPAKKY_SQLALCHEMY__AUTOCOMMIT"] = "true"
    return database_url


@pytest.fixture(name="app", scope="package")
def app_fixture(setup_env_vars: str) -> Generator[SpakkyApplication, Any, None]:
    """Create SpakkyApplication with SQLAlchemy plugins."""
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={
            spakky.plugins.sqlalchemy.PLUGIN_NAME,
            spakky.plugins.outbox_sqlalchemy.PLUGIN_NAME,
        }
    )
    app.start()

    yield app

    app.stop()


@pytest.fixture(name="async_connection_manager", scope="package")
def async_connection_manager_fixture(app: SpakkyApplication) -> AsyncConnectionManager:
    """Get AsyncConnectionManager from application container."""
    return app.container.get(type_=AsyncConnectionManager)


@pytest.fixture(name="schema_registry", scope="package")
def schema_registry_fixture(app: SpakkyApplication) -> SchemaRegistry:
    """Get SchemaRegistry from application container."""
    return app.container.get(type_=SchemaRegistry)


@pytest.fixture(name="setup_database", scope="package", autouse=True)
async def setup_database_fixture(
    async_connection_manager: AsyncConnectionManager,
    schema_registry: SchemaRegistry,
) -> AsyncGenerator[None, Any]:
    """Set up database schema for integration tests."""
    async with async_connection_manager.connection.begin() as conn:
        await conn.run_sync(schema_registry.metadata.create_all)

    yield

    async with async_connection_manager.connection.begin() as conn:
        await conn.run_sync(schema_registry.metadata.drop_all)

    await async_connection_manager.dispose()


@pytest.fixture(name="async_transaction", scope="function")
def async_transaction_fixture(app: SpakkyApplication) -> AsyncTransaction:
    """Get AsyncTransaction from application container."""
    return app.container.get(type_=AsyncTransaction)


@pytest.fixture(name="transaction", scope="function")
def transaction_fixture(app: SpakkyApplication) -> Transaction:
    """Get Transaction from application container."""
    return app.container.get(type_=Transaction)


@pytest.fixture(name="async_storage", scope="function")
def async_storage_fixture(app: SpakkyApplication) -> AsyncSqlAlchemyOutboxStorage:
    """Get AsyncSqlAlchemyOutboxStorage from application container."""
    return app.container.get(type_=AsyncSqlAlchemyOutboxStorage)


@pytest.fixture(name="storage", scope="function")
def storage_fixture(app: SpakkyApplication) -> SqlAlchemyOutboxStorage:
    """Get SqlAlchemyOutboxStorage from application container."""
    return app.container.get(type_=SqlAlchemyOutboxStorage)


@pytest.fixture(name="unique_id", scope="function")
def unique_id_fixture() -> str:
    """Generate unique ID for test data isolation in parallel execution."""
    return uuid4().hex[:8]
