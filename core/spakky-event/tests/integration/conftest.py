"""Integration test fixtures for spakky-event package.

These fixtures set up a complete in-memory event publishing infrastructure
without external dependencies like databases.
"""

from typing import Any, Generator

import pytest
import spakky.data
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)

import spakky.event
from spakky.event import (
    AsyncDomainEventMediator,
    DomainEventMediator,
    IAsyncDomainEventConsumer,
    IDomainEventConsumer,
)
from tests.integration import apps
from tests.integration.apps.handlers.event_recorder import EventRecorder


@Pod()
class InMemoryTransaction(AbstractTransaction):
    """In-memory synchronous transaction for testing."""

    def initialize(self) -> None:
        """No-op initialization."""
        pass

    def dispose(self) -> None:
        """No-op disposal."""
        pass

    def commit(self) -> None:
        """No-op commit."""
        pass

    def rollback(self) -> None:
        """No-op rollback."""
        pass


@Pod()
class InMemoryAsyncTransaction(AbstractAsyncTransaction):
    """In-memory asynchronous transaction for testing."""

    async def initialize(self) -> None:
        """No-op initialization."""
        pass

    async def dispose(self) -> None:
        """No-op disposal."""
        pass

    async def commit(self) -> None:
        """No-op commit."""
        pass

    async def rollback(self) -> None:
        """No-op rollback."""
        pass


@pytest.fixture(name="app", scope="module")
def app_fixture() -> Generator[SpakkyApplication, Any, None]:
    """Create SpakkyApplication with full event publishing infrastructure.

    This fixture sets up:
    - In-memory transactions (sync and async)
    - AggregateCollector (context-scoped)
    - DomainEventMediator (sync and async)
    - DomainEventPublisher (sync and async)
    - TransactionalEventPublishingAspect (sync and async)
    - EventHandlerRegistrationPostProcessor
    - Test handlers and use cases

    Yields:
        Configured SpakkyApplication instance.
    """
    app = (
        SpakkyApplication(ApplicationContext())
        .add(InMemoryTransaction)
        .add(InMemoryAsyncTransaction)
        .load_plugins(include={spakky.event.PLUGIN_NAME, spakky.data.PLUGIN_NAME})
        .scan(apps)
    )
    app.start()

    yield app

    app.stop()


@pytest.fixture(name="event_recorder", scope="function")
def event_recorder_fixture(
    app: SpakkyApplication,
) -> Generator[EventRecorder, Any, None]:
    """Get EventRecorder from application container and clear after each test.

    Args:
        app: SpakkyApplication instance.

    Yields:
        EventRecorder instance, cleared before and after test.
    """
    recorder: EventRecorder = app.container.get(type_=EventRecorder)
    recorder.clear()

    yield recorder

    recorder.clear()


@pytest.fixture(name="collector", scope="function")
def collector_fixture(
    app: SpakkyApplication,
) -> Generator[AggregateCollector, Any, None]:
    """Get AggregateCollector from application container and clear after each test.

    Args:
        app: SpakkyApplication instance.

    Yields:
        AggregateCollector instance, cleared before and after test.
    """
    collector: AggregateCollector = app.container.get(type_=AggregateCollector)
    collector.clear()

    yield collector

    collector.clear()


@pytest.fixture(name="sync_mediator", scope="module")
def sync_mediator_fixture(app: SpakkyApplication) -> DomainEventMediator:
    """Get sync DomainEventMediator from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        DomainEventMediator instance.
    """
    return app.container.get(type_=DomainEventMediator)


@pytest.fixture(name="async_mediator", scope="module")
def async_mediator_fixture(app: SpakkyApplication) -> AsyncDomainEventMediator:
    """Get async DomainEventMediator from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncDomainEventMediator instance.
    """
    return app.container.get(type_=AsyncDomainEventMediator)


@pytest.fixture(name="sync_consumer", scope="module")
def sync_consumer_fixture(app: SpakkyApplication) -> IDomainEventConsumer:
    """Get sync IDomainEventConsumer from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        IDomainEventConsumer instance (DomainEventMediator).
    """
    return app.container.get(type_=IDomainEventConsumer)


@pytest.fixture(name="async_consumer", scope="module")
def async_consumer_fixture(app: SpakkyApplication) -> IAsyncDomainEventConsumer:
    """Get async IAsyncDomainEventConsumer from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        IAsyncDomainEventConsumer instance (AsyncDomainEventMediator).
    """
    return app.container.get(type_=IAsyncDomainEventConsumer)
