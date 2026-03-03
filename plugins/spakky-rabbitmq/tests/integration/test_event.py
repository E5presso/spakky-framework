from asyncio import sleep as asleep  # type: ignore
from time import sleep, time

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.event.error import DuplicateEventHandlerError
from spakky.event.event_consumer import (
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.event_publisher import (
    IAsyncIntegrationEventPublisher,
    IIntegrationEventPublisher,
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
    """동기 이벤트 발행 및 핸들링이 올바르게 동작하는지 검증한다."""
    publisher = app.container.get(IIntegrationEventPublisher)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    publisher.publish(SampleEvent(message="Hello, World!"))
    publisher.publish(SampleEvent(message="Goodbye, World!"))
    wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2


@pytest.mark.asyncio
async def test_asynchronous_event(app: SpakkyApplication) -> None:
    """비동기 이벤트 발행 및 핸들링이 올바르게 동작하는지 검증한다."""
    publisher = app.container.get(IAsyncIntegrationEventPublisher)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    await publisher.publish(SampleEvent(message="Hello, World!"))
    await publisher.publish(SampleEvent(message="Goodbye, World!"))
    await async_wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2


@pytest.mark.asyncio
async def test_async_handler_execution(app: SpakkyApplication) -> None:
    """비동기 컨슈머를 통한 비동기 이벤트 핸들러 실행을 검증한다."""
    publisher = app.container.get(IAsyncIntegrationEventPublisher)
    handler = app.container.get(AsyncEventHandler)

    initial_count = handler.count
    await publisher.publish(AsyncTestEvent(message="Test1"))
    await publisher.publish(AsyncTestEvent(message="Test2"))
    await publisher.publish(AsyncTestEvent(message="Test3"))
    await async_wait_for_count(handler, initial_count + 3)

    # All async events should be handled
    assert handler.count == initial_count + 3


def test_duplicate_handler_registration_sync(app: SpakkyApplication) -> None:
    """중복된 동기 핸들러 등록 시 에러가 발생하는지 검증한다."""
    consumer = app.container.get(IIntegrationEventConsumer)

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
    """중복된 비동기 핸들러 등록 시 에러가 발생하는지 검증한다."""
    consumer = app.container.get(IAsyncIntegrationEventConsumer)

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
