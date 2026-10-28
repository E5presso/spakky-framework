"""Tests for event publisher implementations (type-based router)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import (
    AbstractDomainEvent,
    AbstractEvent,
    AbstractIntegrationEvent,
)

from spakky.event.event_dispatcher import (
    IAsyncEventDispatcher,
    IEventDispatcher,
)
from spakky.event.event_publisher import (
    IAsyncEventBus,
    IEventBus,
)
from spakky.event.publisher.domain_event_publisher import (
    AsyncEventPublisher,
    EventPublisher,
)


@immutable
class SampleDomainEvent(AbstractDomainEvent):
    """Test domain event for publisher tests."""

    data: str


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Test integration event for publisher tests."""

    data: str


class InMemorySyncDispatcher(IEventDispatcher):
    def __init__(self) -> None:
        self.dispatched_events: list[AbstractEvent] = []

    def dispatch(self, event: AbstractEvent) -> None:
        self.dispatched_events.append(event)


class InMemoryAsyncDispatcher(IAsyncEventDispatcher):
    def __init__(self) -> None:
        self.dispatched_events: list[AbstractEvent] = []

    async def dispatch(self, event: AbstractEvent) -> None:
        self.dispatched_events.append(event)


class InMemorySyncBus(IEventBus):
    def __init__(self) -> None:
        self.sent_events: list[AbstractIntegrationEvent] = []

    def send(self, event: AbstractIntegrationEvent) -> None:
        self.sent_events.append(event)


class InMemoryAsyncBus(IAsyncEventBus):
    def __init__(self) -> None:
        self.sent_events: list[AbstractIntegrationEvent] = []

    async def send(self, event: AbstractIntegrationEvent) -> None:
        self.sent_events.append(event)


def test_sync_publisher_routes_domain_event_to_dispatcher() -> None:
    """sync publisher가 domain event를 dispatcher에 위임함을 검증한다."""
    dispatcher = InMemorySyncDispatcher()
    bus = InMemorySyncBus()
    publisher = EventPublisher(dispatcher, bus)

    event = SampleDomainEvent(data="test-data")
    publisher.publish(event)

    assert len(dispatcher.dispatched_events) == 1
    assert dispatcher.dispatched_events[0] is event


def test_sync_publisher_routes_integration_event_to_bus() -> None:
    """sync publisher가 integration event를 bus에 위임함을 검증한다."""
    dispatcher = InMemorySyncDispatcher()
    bus = InMemorySyncBus()
    publisher = EventPublisher(dispatcher, bus)

    event = SampleIntegrationEvent(data="integration-data")
    publisher.publish(event)

    assert len(dispatcher.dispatched_events) == 0
    assert len(bus.sent_events) == 1
    assert bus.sent_events[0] is event


@pytest.mark.asyncio
async def test_async_publisher_routes_domain_event_to_dispatcher() -> None:
    """async publisher가 domain event를 dispatcher에 위임함을 검증한다."""
    dispatcher = InMemoryAsyncDispatcher()
    bus = InMemoryAsyncBus()
    publisher = AsyncEventPublisher(dispatcher, bus)

    event = SampleDomainEvent(data="async-test-data")
    await publisher.publish(event)

    assert len(dispatcher.dispatched_events) == 1
    assert dispatcher.dispatched_events[0] is event


@pytest.mark.asyncio
async def test_async_publisher_routes_integration_event_to_bus() -> None:
    """async publisher가 integration event를 bus에 위임함을 검증한다."""
    dispatcher = InMemoryAsyncDispatcher()
    bus = InMemoryAsyncBus()
    publisher = AsyncEventPublisher(dispatcher, bus)

    event = SampleIntegrationEvent(data="async-integration-data")
    await publisher.publish(event)

    assert len(dispatcher.dispatched_events) == 0
    assert len(bus.sent_events) == 1
    assert bus.sent_events[0] is event


def test_publish_domain_without_dispatcher_expect_explicit_configuration_error() -> (
    None
):
    """Event-only applications cannot silently drop a local domain publish."""
    from spakky.event.error import DomainEventDispatcherUnavailableError

    with pytest.raises(DomainEventDispatcherUnavailableError):
        EventPublisher(None, MagicMock()).publish(
            SampleDomainEvent(data="missing local provider")
        )


async def test_publish_async_domain_without_dispatcher_expect_explicit_configuration_error() -> (
    None
):
    """The missing local provider fails equally in async publishing."""
    from spakky.event.error import DomainEventDispatcherUnavailableError

    with pytest.raises(DomainEventDispatcherUnavailableError):
        await AsyncEventPublisher(None, AsyncMock()).publish(
            SampleDomainEvent(data="missing local provider")
        )
