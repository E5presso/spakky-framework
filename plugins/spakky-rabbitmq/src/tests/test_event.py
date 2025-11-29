from asyncio import sleep as asleep  # pyrefly: ignore  # type: ignore
from time import sleep, time

import pytest
from spakky.application.application import SpakkyApplication
from spakky.domain.ports.event.error import DuplicateEventHandlerError
from spakky.domain.ports.event.event_consumer import IAsyncEventConsumer, IEventConsumer
from spakky.domain.ports.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)

from tests.apps.dummy import (
    AsyncEventHandler,
    AsyncTestEvent,
    DummyEventHandler,
    DuplicateTestEvent,
    SampleEvent,
)

POLL_INTERVAL = 0.05  # seconds between checks
MAX_WAIT_TIME = 10  # maximum seconds to wait


def wait_for_count(
    handler: DummyEventHandler | AsyncEventHandler, expected: int
) -> None:
    """Poll until handler.count reaches expected value or timeout."""
    start = time()
    while handler.count < expected:
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError(
                f"Timed out waiting for handler.count to reach {expected}. "
                f"Current count: {handler.count}"
            )
        sleep(POLL_INTERVAL)


async def async_wait_for_count(
    handler: DummyEventHandler | AsyncEventHandler, expected: int
) -> None:
    """Async poll until handler.count reaches expected value or timeout."""
    start = time()
    while handler.count < expected:
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError(
                f"Timed out waiting for handler.count to reach {expected}. "
                f"Current count: {handler.count}"
            )
        await asleep(POLL_INTERVAL)


def test_synchronous_event(app: SpakkyApplication) -> None:
    publisher = app.container.get(IEventPublisher)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    publisher.publish(SampleEvent(message="Hello, World!"))
    publisher.publish(SampleEvent(message="Goodbye, World!"))
    wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2
    assert len(handler.context_ids) >= 2


@pytest.mark.asyncio
async def test_asynchronous_event(app: SpakkyApplication) -> None:
    publisher = app.container.get(IAsyncEventPublisher)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    await publisher.publish(SampleEvent(message="Hello, World!"))
    await publisher.publish(SampleEvent(message="Goodbye, World!"))
    await async_wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2
    assert len(handler.context_ids) >= 2


@pytest.mark.asyncio
async def test_async_handler_execution(app: SpakkyApplication) -> None:
    """Test async event handler execution via async consumer."""
    publisher = app.container.get(IAsyncEventPublisher)
    handler = app.container.get(AsyncEventHandler)

    initial_count = handler.count
    await publisher.publish(AsyncTestEvent(message="Test1"))
    await publisher.publish(AsyncTestEvent(message="Test2"))
    await publisher.publish(AsyncTestEvent(message="Test3"))
    await async_wait_for_count(handler, initial_count + 3)

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

    assert DuplicateTestEvent in exc_info.value.args


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

    assert DuplicateTestEvent in exc_info.value.args
