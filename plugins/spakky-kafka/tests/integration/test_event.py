from asyncio import sleep as asleep
from os import environ
from time import sleep, time

import pytest
from confluent_kafka import Consumer, Message
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

from spakky.plugins.kafka.common.config import AutoOffsetResetType
from spakky.plugins.kafka.common.constants import (
    SPAKKY_KAFKA_CONFIG_ENV_PREFIX,
    DeadLetterHeaderKey,
)
from spakky.plugins.kafka.event.consumer import (
    AsyncKafkaEventConsumer,
    KafkaEventConsumer,
)
from tests.apps.dummy import (
    AsyncFailingEvent,
    DummyEventHandler,
    DuplicateTestEvent,
    FailingEvent,
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
    transport.flush()
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
    await transport.flush()
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


def decode_headers(record: Message) -> dict[str, str]:
    """Decode the byte-valued Kafka headers of a record for assertion."""
    return {
        key: value.decode()
        for key, value in (record.headers() or [])
        if isinstance(value, bytes)
    }


def read_dead_letter_record(topic: str) -> Message:
    """Consume the single record the consumer routed to `topic`, or time out."""
    dead_letter_consumer = Consumer(
        {
            "group.id": f"dead-letter-reader-{topic}",
            "client.id": f"dead-letter-reader-{topic}",
            "bootstrap.servers": environ[
                f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS"
            ],
            "auto.offset.reset": AutoOffsetResetType.EARLIEST.value,
        }
    )
    dead_letter_consumer.subscribe([topic])
    try:
        start = time()
        while time() - start <= MAX_WAIT_TIME:
            record = dead_letter_consumer.poll(timeout=POLL_INTERVAL)
            if record is not None and record.error() is None:
                return record
        raise TimeoutError(f"No dead-letter record arrived on {topic}")
    finally:
        dead_letter_consumer.close()


def test_synchronous_handler_failure_expect_dead_letter_record(
    app: SpakkyApplication,
) -> None:
    """동기 핸들러가 실패한 메시지가 dead-letter 토픽에서 원본 본문·헤더와 함께 관찰된다."""
    transport = app.container.get(IEventTransport)
    event = FailingEvent(message="sync-poison")
    payload = TypeAdapter(FailingEvent).dump_json(event)

    transport.send("FailingEvent", payload, {})
    transport.flush()

    record = read_dead_letter_record("FailingEvent.dlt")
    assert record.value() == payload
    headers = decode_headers(record)
    assert headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == "FailingEvent"
    assert headers[DeadLetterHeaderKey.CONSUMER_GROUP] == "test-group"
    assert headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == "RuntimeError"
    assert (
        "cannot process sync-poison" in headers[DeadLetterHeaderKey.EXCEPTION_MESSAGE]
    )


@pytest.mark.asyncio
async def test_asynchronous_handler_failure_expect_dead_letter_record(
    app: SpakkyApplication,
) -> None:
    """비동기 핸들러가 실패한 메시지가 dead-letter 토픽에서 원본 본문·헤더와 함께 관찰된다."""
    transport = app.container.get(IAsyncEventTransport)
    event = AsyncFailingEvent(message="async-poison")
    payload = TypeAdapter(AsyncFailingEvent).dump_json(event)

    await transport.send("AsyncFailingEvent", payload, {})
    await transport.flush()

    record = read_dead_letter_record("AsyncFailingEvent.dlt")
    assert record.value() == payload
    headers = decode_headers(record)
    assert headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == "AsyncFailingEvent"
    assert headers[DeadLetterHeaderKey.CONSUMER_GROUP] == "test-group"
    assert headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == "RuntimeError"
    assert (
        "cannot process async-poison" in headers[DeadLetterHeaderKey.EXCEPTION_MESSAGE]
    )
