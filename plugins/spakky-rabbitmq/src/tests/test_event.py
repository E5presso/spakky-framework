from asyncio import sleep as asleep  # pyrefly: ignore
from time import sleep

import pytest
from spakky.application.application import SpakkyApplication
from spakky.domain.ports.event.event_consumer import IAsyncEventConsumer, IEventConsumer
from spakky.domain.ports.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)

from spakky_rabbitmq.error import DuplicateEventHandlerError
from tests.apps.dummy import (
    AsyncEventHandler,
    AsyncTestEvent,
    DummyEventHandler,
    DuplicateTestEvent,
    SampleEvent,
)


def test_synchronous_event(app: SpakkyApplication) -> None:
    publisher = app.container.get(IEventPublisher)
    publisher.publish(SampleEvent(message="Hello, World!"))
    publisher.publish(SampleEvent(message="Goodbye, World!"))
    sleep(0.1)
    handler = app.container.get(DummyEventHandler)
    assert handler.count == 2
    assert len(handler.context_ids) == 2


@pytest.mark.asyncio
async def test_asynchronous_event(app: SpakkyApplication) -> None:
    publisher = app.container.get(IAsyncEventPublisher)
    await publisher.publish(SampleEvent(message="Hello, World!"))
    await publisher.publish(SampleEvent(message="Goodbye, World!"))
    await asleep(0.1)
    handler = app.container.get(DummyEventHandler)
    assert handler.count == 2
    assert len(handler.context_ids) == 2


@pytest.mark.asyncio
async def test_async_handler_execution(app: SpakkyApplication) -> None:
    """Test async event handler execution via async consumer."""
    publisher = app.container.get(IAsyncEventPublisher)
    handler = app.container.get(AsyncEventHandler)

    initial_count = handler.count
    await publisher.publish(AsyncTestEvent(message="Test1"))
    await publisher.publish(AsyncTestEvent(message="Test2"))
    await publisher.publish(AsyncTestEvent(message="Test3"))
    await asleep(0.1)

    # All async events should be handled
    assert handler.count == initial_count + 3


def test_duplicate_handler_registration_sync(app: SpakkyApplication) -> None:
    """Test that registering duplicate sync handler raises error."""
    consumer = app.container.get(IEventConsumer)

    def handler1(event: DuplicateTestEvent) -> None:
        pass

    def handler2(event: DuplicateTestEvent) -> None:
        pass

    # First registration should succeed
    consumer.register(DuplicateTestEvent, handler1)

    # Second registration for same event type should fail
    with pytest.raises(DuplicateEventHandlerError) as exc_info:
        consumer.register(DuplicateTestEvent, handler2)

    assert exc_info.value.event_type == DuplicateTestEvent
    assert "DuplicateTestEvent" in str(exc_info.value)
    assert "already registered" in str(exc_info.value)


@pytest.mark.asyncio
async def test_duplicate_handler_registration_async(app: SpakkyApplication) -> None:
    """Test that registering duplicate async handler raises error."""
    consumer = app.container.get(IAsyncEventConsumer)

    async def handler1(event: DuplicateTestEvent) -> None:
        pass

    async def handler2(event: DuplicateTestEvent) -> None:
        pass

    # First registration should succeed
    consumer.register(DuplicateTestEvent, handler1)

    # Second registration for same event type should fail
    with pytest.raises(DuplicateEventHandlerError) as exc_info:
        consumer.register(DuplicateTestEvent, handler2)

    assert exc_info.value.event_type == DuplicateTestEvent
    assert "DuplicateTestEvent" in str(exc_info.value)
    assert "already registered" in str(exc_info.value)
