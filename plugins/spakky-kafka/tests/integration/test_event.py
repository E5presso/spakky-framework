from asyncio import sleep as asleep
from time import sleep, time

import pytest
from pydantic import TypeAdapter
from spakky.core.application.application import SpakkyApplication
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.event_publisher import (
    IAsyncEventTransport,
    IEventTransport,
)

from spakky.plugins.kafka.event.consumer import (
    AsyncKafkaEventConsumer,
    KafkaEventConsumer,
)
from tests.apps.dummy import (
    DummyEventHandler,
    DuplicateTestEvent,
    SampleEvent,
)

POLL_INTERVAL = 0.05  # seconds between checks
MAX_WAIT_TIME = 10  # maximum seconds to wait

_sample_event_type_adapter: TypeAdapter[SampleEvent] = TypeAdapter(SampleEvent)


def wait_for_count(handler: DummyEventHandler, expected: int) -> None:
    """Poll until handler.count reaches expected value or timeout."""
    start = time()
    while handler.count < expected:
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError(
                f"Timed out waiting for handler.count to reach {expected}. "
                f"Current count: {handler.count}"
            )
        sleep(POLL_INTERVAL)


async def async_wait_for_count(handler: DummyEventHandler, expected: int) -> None:
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
    transport = app.container.get(IEventTransport)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    event1 = SampleEvent(message="Hello, World!")
    event2 = SampleEvent(message="Goodbye, World!")
    transport.send("SampleEvent", _sample_event_type_adapter.dump_json(event1), {})
    transport.send("SampleEvent", _sample_event_type_adapter.dump_json(event2), {})
    wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2


@pytest.mark.asyncio
async def test_asynchronous_event(app: SpakkyApplication) -> None:
    """비동기 이벤트 발행 및 핸들링이 올바르게 동작하는지 검증한다."""
    transport = app.container.get(IAsyncEventTransport)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    event1 = SampleEvent(message="Hello, World!")
    event2 = SampleEvent(message="Goodbye, World!")
    await transport.send(
        "SampleEvent", _sample_event_type_adapter.dump_json(event1), {}
    )
    await transport.send(
        "SampleEvent", _sample_event_type_adapter.dump_json(event2), {}
    )
    await async_wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2


def test_multiple_handler_registration_sync(app: SpakkyApplication) -> None:
    """동일 이벤트에 복수 동기 핸들러 등록이 정상 동작하는지 검증한다."""
    consumer = app.container.get(IEventConsumer)
    assert isinstance(consumer, KafkaEventConsumer)

    def handler1(event: DuplicateTestEvent) -> None:
        pass

    def handler2(event: DuplicateTestEvent) -> None:
        pass

    consumer.register(DuplicateTestEvent, handler1)
    consumer.register(DuplicateTestEvent, handler2)

    assert len(consumer.handlers[DuplicateTestEvent]) == 2


@pytest.mark.asyncio
async def test_multiple_handler_registration_async(app: SpakkyApplication) -> None:
    """동일 이벤트에 복수 비동기 핸들러 등록이 정상 동작하는지 검증한다."""
    consumer = app.container.get(IAsyncEventConsumer)
    assert isinstance(consumer, AsyncKafkaEventConsumer)

    async def handler1(event: DuplicateTestEvent) -> None:
        pass

    async def handler2(event: DuplicateTestEvent) -> None:
        pass

    consumer.register(DuplicateTestEvent, handler1)
    consumer.register(DuplicateTestEvent, handler2)

    assert len(consumer.handlers[DuplicateTestEvent]) == 2
