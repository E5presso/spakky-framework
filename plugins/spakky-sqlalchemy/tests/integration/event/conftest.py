"""Integration fixtures: SQLAlchemy inbox with the in-memory event broker on PostgreSQL."""

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import spakky.data
import spakky.event
import spakky.tracing
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.event.memory.main import initialize as initialize_memory_broker
from testcontainers.postgres import PostgresContainer

import spakky.plugins.sqlalchemy
from spakky.plugins.sqlalchemy.contributions.event import (
    initialize as initialize_event_contribution,
)
from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.connection_manager import (
    AsyncConnectionManager,
)
from tests.integration.event import handlers


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


@pytest.fixture(name="app", scope="package")
def app_fixture(
    postgres_container: PostgresContainer,
) -> Generator[SpakkyApplication, Any, None]:
    """Application with SQLAlchemy, the inbox contribution and the memory broker."""
    os.environ["SPAKKY_SQLALCHEMY__CONNECTION_STRING"] = (
        postgres_container.get_connection_url()
        .replace("psycopg2", "psycopg")
        .replace("postgresql://", "postgresql+psycopg://")
    )
    os.environ["SPAKKY_SQLALCHEMY__ECHO"] = "false"
    os.environ["SPAKKY_SQLALCHEMY__AUTOCOMMIT"] = "true"
    os.environ["SPAKKY_EVENT_MEMORY__RETRY__MAX_ATTEMPTS"] = "2"
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={
            spakky.plugins.sqlalchemy.PLUGIN_NAME,
            spakky.data.PLUGIN_NAME,
            spakky.event.PLUGIN_NAME,
            spakky.tracing.PLUGIN_NAME,
        }
    )
    initialize_event_contribution(app)
    initialize_memory_broker(app)
    for pod in (
        handlers.LedgerEntryTable,
        handlers.LedgerHandler,
        handlers.ReportingHandler,
        handlers.AsyncLedgerHandler,
    ):
        app.add(pod)
    app.start()

    yield app

    app.stop()
    del os.environ["SPAKKY_EVENT_MEMORY__RETRY__MAX_ATTEMPTS"]


@pytest.fixture(name="setup_database", scope="package", autouse=True)
async def setup_database_fixture(
    app: SpakkyApplication,
) -> AsyncGenerator[None, Any]:
    """Create the schema, including the inbox and ledger tables."""
    connection_manager = app.container.get(type_=AsyncConnectionManager)
    metadata = app.container.get(type_=SchemaRegistry).metadata
    async with connection_manager.connection.begin() as conn:
        await conn.run_sync(metadata.create_all)

    yield

    async with connection_manager.connection.begin() as conn:
        await conn.run_sync(metadata.drop_all)
    await connection_manager.dispose()
