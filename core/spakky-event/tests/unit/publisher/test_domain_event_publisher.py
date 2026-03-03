"""Tests for domain event publisher implementations."""

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent

from spakky.event.event_dispatcher import (
    IAsyncDomainEventDispatcher,
    IDomainEventDispatcher,
)
from spakky.event.publisher.domain_event_publisher import (
    AsyncDomainEventPublisher,
    DomainEventPublisher,
)


@immutable
class TestEvent(AbstractDomainEvent):
    """Test event for publisher tests."""

    data: str


class InMemorySyncDispatcher(IDomainEventDispatcher):
    """In-memory synchronous dispatcher for testing."""

    def __init__(self) -> None:
        self.dispatched_events: list[AbstractDomainEvent] = []

    def dispatch(self, event: AbstractDomainEvent) -> None:
        self.dispatched_events.append(event)


class InMemoryAsyncDispatcher(IAsyncDomainEventDispatcher):
    """In-memory asynchronous dispatcher for testing."""

    def __init__(self) -> None:
        self.dispatched_events: list[AbstractDomainEvent] = []

    async def dispatch(self, event: AbstractDomainEvent) -> None:
        self.dispatched_events.append(event)


def test_sync_publisher_publishes_to_dispatcher() -> None:
    """Test that sync publisher delegates to dispatcher."""
    dispatcher = InMemorySyncDispatcher()
    publisher = DomainEventPublisher(dispatcher)

    event = TestEvent(data="test-data")
    publisher.publish(event)

    assert len(dispatcher.dispatched_events) == 1
    assert dispatcher.dispatched_events[0] is event


def test_sync_publisher_publishes_multiple_events() -> None:
    """Test that sync publisher handles multiple publishes."""
    dispatcher = InMemorySyncDispatcher()
    publisher = DomainEventPublisher(dispatcher)

    event1 = TestEvent(data="event-1")
    event2 = TestEvent(data="event-2")

    publisher.publish(event1)
    publisher.publish(event2)

    assert len(dispatcher.dispatched_events) == 2
    dispatched1 = dispatcher.dispatched_events[0]
    dispatched2 = dispatcher.dispatched_events[1]
    assert isinstance(dispatched1, TestEvent) and dispatched1.data == "event-1"
    assert isinstance(dispatched2, TestEvent) and dispatched2.data == "event-2"


@pytest.mark.asyncio
async def test_async_publisher_publishes_to_dispatcher() -> None:
    """Test that async publisher delegates to dispatcher."""
    dispatcher = InMemoryAsyncDispatcher()
    publisher = AsyncDomainEventPublisher(dispatcher)

    event = TestEvent(data="async-test-data")
    await publisher.publish(event)

    assert len(dispatcher.dispatched_events) == 1
    assert dispatcher.dispatched_events[0] is event


@pytest.mark.asyncio
async def test_async_publisher_publishes_multiple_events() -> None:
    """Test that async publisher handles multiple publishes."""
    dispatcher = InMemoryAsyncDispatcher()
    publisher = AsyncDomainEventPublisher(dispatcher)

    event1 = TestEvent(data="async-event-1")
    event2 = TestEvent(data="async-event-2")

    await publisher.publish(event1)
    await publisher.publish(event2)

    assert len(dispatcher.dispatched_events) == 2
    dispatched1 = dispatcher.dispatched_events[0]
    dispatched2 = dispatcher.dispatched_events[1]
    assert isinstance(dispatched1, TestEvent) and dispatched1.data == "async-event-1"
    assert isinstance(dispatched2, TestEvent) and dispatched2.data == "async-event-2"
