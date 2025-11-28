from asyncio import sleep as asleep  # pyrefly: ignore  # type: ignore
from time import sleep

import pytest
from spakky.application.application import SpakkyApplication
from spakky.domain.ports.event.error import DuplicateEventHandlerError
from spakky.domain.ports.event.event_consumer import IAsyncEventConsumer, IEventConsumer
from spakky.domain.ports.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)

from tests.apps.dummy import (
    DummyEventHandler,
    DuplicateTestEvent,
    SampleEvent,
)

DELAY_AFTER_PUBLISH = 3  # seconds


def test_synchronous_event(app: SpakkyApplication) -> None:
    publisher = app.container.get(IEventPublisher)
    publisher.publish(SampleEvent(message="Hello, World!"))
    publisher.publish(SampleEvent(message="Goodbye, World!"))
    sleep(DELAY_AFTER_PUBLISH)
    handler = app.container.get(DummyEventHandler)
    assert handler.count == 2
    assert len(handler.context_ids) == 2


@pytest.mark.asyncio
async def test_asynchronous_event(app: SpakkyApplication) -> None:
    publisher = app.container.get(IAsyncEventPublisher)
    await publisher.publish(SampleEvent(message="Hello, World!"))
    await publisher.publish(SampleEvent(message="Goodbye, World!"))
    await asleep(DELAY_AFTER_PUBLISH)
    handler = app.container.get(DummyEventHandler)
    assert handler.count == 2
    assert len(handler.context_ids) == 2


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
