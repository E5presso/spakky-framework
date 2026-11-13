"""Real broker scenarios of the per-subscriber delivery contract."""

import asyncio
import threading
from collections import Counter
from collections.abc import Awaitable, Callable
from time import monotonic, sleep
from typing import override
from uuid import uuid4

from confluent_kafka import Consumer, Message, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.delivery import (
    DeadLetter,
    DeliveryHeader,
    DeliveryState,
    RetryMode,
    RetryPolicy,
)
from spakky.event.redrive import RedriveResult

from spakky.plugins.kafka.common.config import (
    AutoOffsetResetType,
    KafkaConnectionConfig,
)
from spakky.plugins.kafka.common.constants import DeadLetterHeaderKey
from spakky.plugins.kafka.event.consumer import (
    AsyncKafkaEventConsumer,
    KafkaEventConsumer,
)

MAX_WAIT_TIME = 30
"""Diagnostic deadline in seconds for one broker observation."""

POLL_INTERVAL = 0.05
"""Seconds between two checks of a broker observation."""

RUN_ID = uuid4().hex
"""Keeps topics and groups of this run apart from earlier runs on a reused broker."""


@immutable
class FanOutEvent(AbstractIntegrationEvent):
    """Event read by two subscribers that both succeed."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.fanout.{RUN_ID}"


@immutable
class IsolatedEvent(AbstractIntegrationEvent):
    """Event one subscriber always fails on while another succeeds."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.isolated.{RUN_ID}"


@immutable
class BlockingRetryEvent(AbstractIntegrationEvent):
    """Event whose failed handler is retried in place."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.blocking.{RUN_ID}"


@immutable
class DelayedRetryEvent(AbstractIntegrationEvent):
    """Event whose failed handler is retried through the retry topic."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.delayed.{RUN_ID}"


@immutable
class RestartedRetryEvent(AbstractIntegrationEvent):
    """Event whose retry record waits across a consumer restart."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.restarted.{RUN_ID}"


@immutable
class RedrivenEvent(AbstractIntegrationEvent):
    """Event dead-lettered by one handler and redriven later."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.redriven.{RUN_ID}"


@immutable
class SyncIsolatedEvent(AbstractIntegrationEvent):
    """Event the synchronous consumer dead-letters for one subscriber only."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.sync.isolated.{RUN_ID}"


@immutable
class SyncRetryEvent(AbstractIntegrationEvent):
    """Event the synchronous consumer retries in place."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.subscribers.sync.retry.{RUN_ID}"


def make_config(retry: RetryPolicy) -> KafkaConnectionConfig:
    """Build a config with its own base group so runs never share offsets."""
    config = KafkaConnectionConfig()
    config.group_id = f"subscribers-{uuid4().hex}"
    config.poll_timeout = POLL_INTERVAL
    config.retry = retry
    return config


def publish(
    config: KafkaConnectionConfig, events: list[AbstractIntegrationEvent]
) -> None:
    """Publish events to their own topics and wait for the broker to confirm."""
    producer = Producer(config.producer_configuration_dict)
    for event in events:
        producer.produce(
            event.event_name,
            value=TypeAdapter(type(event)).dump_json(event),
            key=b"key",
            headers={"x-custom": "kept"},
        )
    assert producer.flush(MAX_WAIT_TIME) == 0


def end_offset(config: KafkaConnectionConfig, topic: str) -> int:
    """Return how many records a single-partition topic holds."""
    inspector = Consumer(
        {**config.consumer_configuration_dict, "group.id": "inspector"}
    )
    try:
        return inspector.get_watermark_offsets(
            TopicPartition(topic, 0), timeout=MAX_WAIT_TIME
        )[1]
    finally:
        inspector.close()


def committed_offset(config: KafkaConnectionConfig, group_id: str, topic: str) -> int:
    """Return the offset a group committed on a single-partition topic."""
    inspector = Consumer({**config.consumer_configuration_dict, "group.id": group_id})
    try:
        return inspector.committed([TopicPartition(topic, 0)], timeout=MAX_WAIT_TIME)[
            0
        ].offset
    finally:
        inspector.close()


def read_records(
    config: KafkaConnectionConfig, topic: str, count: int
) -> list[Message]:
    """Read the first `count` records of a topic, bounded by a diagnostic deadline."""
    reader = Consumer(
        {
            **config.consumer_configuration_dict,
            "group.id": f"reader-{uuid4().hex}",
            "auto.offset.reset": "earliest",
        }
    )
    reader.assign([TopicPartition(topic, 0, 0)])
    records: list[Message] = []
    try:
        deadline = monotonic() + MAX_WAIT_TIME
        while len(records) < count:
            if monotonic() > deadline:
                raise TimeoutError(f"Only {len(records)}/{count} records on {topic}")
            record = reader.poll(timeout=POLL_INTERVAL)
            if record is not None and record.error() is None:
                records.append(record)
        return records
    finally:
        reader.close()


def decode_headers(record: Message) -> dict[str, str]:
    """Decode the byte-valued Kafka headers of a record for assertion."""
    return {
        key: value.decode()
        for key, value in (record.headers() or [])
        if isinstance(value, bytes)
    }


async def eventually(predicate: Callable[[], Awaitable[bool] | bool]) -> None:
    """Wait for a concrete observation, bounded by a diagnostic deadline."""
    async with asyncio.timeout(MAX_WAIT_TIME):
        while True:
            result = predicate()
            if isinstance(result, Awaitable):
                result = await result
            if result:
                return
            await asyncio.sleep(POLL_INTERVAL)


def wait_until(predicate: Callable[[], bool]) -> None:
    """Block until a concrete observation holds, bounded by a diagnostic deadline."""
    deadline = monotonic() + MAX_WAIT_TIME
    while not predicate():
        if monotonic() > deadline:
            raise TimeoutError("Observation did not hold before the deadline")
        sleep(POLL_INTERVAL)


async def test_two_subscribers_expect_each_receives_every_message() -> None:
    """두 구독자가 같은 이벤트 스트림을 각자의 그룹 오프셋으로 전부 읽는다."""
    config = make_config(RetryPolicy())
    topic = FanOutEvent(value="probe").event_name
    received: dict[str, list[str]] = {"billing": [], "shipping": []}

    async def bill(event: FanOutEvent) -> None:
        received["billing"].append(event.value)

    async def ship(event: FanOutEvent) -> None:
        received["shipping"].append(event.value)

    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    consumer.register(FanOutEvent, bill, subscriber="billing", handler_name="bill")
    consumer.register(FanOutEvent, ship, subscriber="shipping", handler_name="ship")
    await consumer.start_async()
    try:
        publish(config, [FanOutEvent(value=value) for value in ("a", "b", "c")])

        await eventually(
            lambda: len(received["billing"]) == 3 and len(received["shipping"]) == 3
        )
        assert received == {"billing": ["a", "b", "c"], "shipping": ["a", "b", "c"]}

        async def both_committed() -> bool:
            offsets = [
                await asyncio.to_thread(
                    committed_offset, config, f"{config.group_id}.{name}", topic
                )
                for name in ("billing", "shipping")
            ]
            return offsets == [3, 3]

        await eventually(both_committed)
    finally:
        await consumer.stop_async()


async def test_failing_subscriber_expect_own_dead_letter_while_other_proceeds() -> None:
    """항상 실패하는 구독자만 자기 DLT로 보내고 다른 구독자는 그대로 진행한다."""
    config = make_config(RetryPolicy(max_attempts=2, initial_interval=0.1))
    topic = IsolatedEvent(value="probe").event_name
    shipped: list[str] = []
    charges: Counter[str] = Counter()

    async def charge(event: IsolatedEvent) -> None:
        charges[event.value] += 1
        raise RuntimeError(f"cannot charge {event.value}")

    async def ship(event: IsolatedEvent) -> None:
        shipped.append(event.value)

    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    consumer.register(
        IsolatedEvent, charge, subscriber="billing", handler_name="charge"
    )
    consumer.register(IsolatedEvent, ship, subscriber="shipping", handler_name="ship")
    await consumer.start_async()
    try:
        events = [IsolatedEvent(value="first"), IsolatedEvent(value="second")]
        publish(config, list(events))

        records = await asyncio.to_thread(
            read_records, config, f"{topic}.billing.dlt", 2
        )

        assert [record.value() for record in records] == [
            TypeAdapter(IsolatedEvent).dump_json(event) for event in events
        ]
        assert records[0].key() == b"key"
        headers = decode_headers(records[0])
        assert headers["x-custom"] == "kept"
        assert headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == topic
        assert headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "0"
        assert headers[DeadLetterHeaderKey.CONSUMER_GROUP] == (
            f"{config.group_id}.billing"
        )
        assert headers[DeadLetterHeaderKey.EXCEPTION_TYPE] == "RuntimeError"
        dead_letter = DeadLetter.from_headers(headers)
        assert dead_letter.event_name == topic
        assert dead_letter.subscriber == "billing"
        assert dead_letter.attempts == 2
        assert [failure.handler for failure in dead_letter.failures] == ["charge"]
        assert dead_letter.failures[0].exception_message == "cannot charge first"
        assert charges == {"first": 2, "second": 2}
        await eventually(lambda: shipped == ["first", "second"])
        assert await asyncio.to_thread(end_offset, config, f"{topic}.shipping.dlt") == 0
    finally:
        await consumer.stop_async()


async def test_blocking_retry_expect_other_handler_runs_and_only_failed_handler_reruns() -> (
    None
):
    """한 핸들러의 실패가 같은 구독자의 다른 핸들러를 막지 않고, 재시도는 실패한 핸들러만 다시 실행한다."""
    config = make_config(RetryPolicy(max_attempts=3, initial_interval=0.1))
    topic = BlockingRetryEvent(value="probe").event_name
    calls: Counter[str] = Counter()
    order: list[str] = []

    async def flaky(event: BlockingRetryEvent) -> None:
        calls["flaky"] += 1
        if event.value == "first" and calls["flaky"] == 1:
            raise RuntimeError("first attempt fails")
        order.append(event.value)

    async def steady(event: BlockingRetryEvent) -> None:
        calls[f"steady:{event.value}"] += 1

    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    consumer.register(
        BlockingRetryEvent, flaky, subscriber="orders", handler_name="flaky"
    )
    consumer.register(
        BlockingRetryEvent, steady, subscriber="orders", handler_name="steady"
    )
    await consumer.start_async()
    try:
        publish(
            config,
            [BlockingRetryEvent(value="first"), BlockingRetryEvent(value="second")],
        )

        async def committed() -> bool:
            return (
                await asyncio.to_thread(
                    committed_offset, config, f"{config.group_id}.orders", topic
                )
                == 2
            )

        await eventually(committed)
        assert calls == {"flaky": 3, "steady:first": 1, "steady:second": 1}
        assert order == ["first", "second"]
        assert await asyncio.to_thread(end_offset, config, f"{topic}.orders.dlt") == 0
    finally:
        await consumer.stop_async()


async def test_delayed_retry_expect_retry_topic_record_and_later_messages_not_blocked() -> (
    None
):
    """DELAYED 재시도는 retry 토픽을 거치고, 기다리는 동안 뒤 메시지가 먼저 처리된다."""
    config = make_config(
        RetryPolicy(max_attempts=3, initial_interval=2.0, mode=RetryMode.DELAYED)
    )
    topic = DelayedRetryEvent(value="probe").event_name
    calls: Counter[str] = Counter()
    order: list[str] = []

    async def flaky(event: DelayedRetryEvent) -> None:
        calls[f"flaky:{event.value}"] += 1
        if event.value == "first" and calls["flaky:first"] == 1:
            raise RuntimeError("first attempt fails")
        order.append(event.value)

    async def steady(event: DelayedRetryEvent) -> None:
        calls[f"steady:{event.value}"] += 1

    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    consumer.register(
        DelayedRetryEvent, flaky, subscriber="orders", handler_name="flaky"
    )
    consumer.register(
        DelayedRetryEvent, steady, subscriber="orders", handler_name="steady"
    )
    await consumer.start_async()
    try:
        events = [DelayedRetryEvent(value="first"), DelayedRetryEvent(value="second")]
        publish(config, list(events))

        await eventually(lambda: order == ["second", "first"])

        assert calls == {
            "flaky:first": 2,
            "flaky:second": 1,
            "steady:first": 1,
            "steady:second": 1,
        }
        records = await asyncio.to_thread(
            read_records, config, f"{topic}.orders.retry", 1
        )
        headers = decode_headers(records[0])
        assert records[0].value() == TypeAdapter(DelayedRetryEvent).dump_json(events[0])
        assert DeliveryState.from_headers(headers) == DeliveryState(
            attempt=2, pending=frozenset({"flaky"})
        )
        assert float(headers[DeliveryHeader.NOT_BEFORE]) > 0
        assert headers[DeadLetterHeaderKey.ORIGINAL_TOPIC] == topic
        assert headers[DeadLetterHeaderKey.ORIGINAL_OFFSET] == "0"

        async def retry_committed() -> bool:
            return (
                await asyncio.to_thread(
                    committed_offset,
                    config,
                    f"{config.group_id}.orders",
                    f"{topic}.orders.retry",
                )
                == 1
            )

        await eventually(retry_committed)
        assert await asyncio.to_thread(end_offset, config, f"{topic}.orders.retry") == 1
        assert await asyncio.to_thread(end_offset, config, f"{topic}.orders.dlt") == 0
    finally:
        await consumer.stop_async()


async def test_redrive_expect_only_failed_subscriber_and_only_failed_handler() -> None:
    """redrive는 실패한 구독자의 실패한 핸들러만 다시 실행하고, 다시 실패하면 DLT에 남긴다."""
    config = make_config(RetryPolicy())
    topic = RedrivenEvent(value="probe").event_name
    calls: Counter[str] = Counter()
    gateway_up = False

    async def charge(event: RedrivenEvent) -> None:
        calls["charge"] += 1
        if not gateway_up:
            raise RuntimeError(f"gateway down for {event.value}")
        calls["charged"] += 1

    async def audit(event: RedrivenEvent) -> None:
        calls["audit"] += 1

    async def ship(event: RedrivenEvent) -> None:
        calls["ship"] += 1

    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    consumer.register(
        RedrivenEvent, charge, subscriber="billing", handler_name="charge"
    )
    consumer.register(RedrivenEvent, audit, subscriber="billing", handler_name="audit")
    consumer.register(RedrivenEvent, ship, subscriber="shipping", handler_name="ship")
    await consumer.start_async()
    try:
        publish(config, [RedrivenEvent(value="first"), RedrivenEvent(value="second")])
        await asyncio.to_thread(read_records, config, f"{topic}.billing.dlt", 2)
        await eventually(lambda: calls["ship"] == 2)
        assert calls == {"charge": 2, "audit": 2, "ship": 2}

        still_failing = await consumer.redrive(
            RedrivenEvent, subscriber="billing", limit=1
        )

        assert still_failing == RedriveResult(succeeded=0, failed=1)
        assert calls == {"charge": 3, "audit": 2, "ship": 2}
        records = await asyncio.to_thread(
            read_records, config, f"{topic}.billing.dlt", 3
        )
        republished = DeadLetter.from_headers(decode_headers(records[2]))
        assert republished.attempts == 2
        assert republished.pending == frozenset({"charge"})
        assert records[2].value() == records[0].value()
        assert decode_headers(records[2])[DeadLetterHeaderKey.ORIGINAL_TOPIC] == topic

        gateway_up = True
        recovered = await consumer.redrive(RedrivenEvent, subscriber="billing")
        nothing_left = await consumer.redrive(RedrivenEvent, subscriber="billing")

        assert recovered == RedriveResult(succeeded=2, failed=0)
        assert nothing_left == RedriveResult(succeeded=0, failed=0)
        assert calls == {"charge": 5, "charged": 2, "audit": 2, "ship": 2}
        assert await asyncio.to_thread(end_offset, config, f"{topic}.billing.dlt") == 3
        assert (
            await asyncio.to_thread(
                committed_offset,
                config,
                f"{config.group_id}.billing.redrive",
                f"{topic}.billing.dlt",
            )
            == 3
        )
    finally:
        await consumer.stop_async()


def test_sync_failing_subscriber_expect_own_dead_letter_and_redrive_to_it_only() -> (
    None
):
    """동기 소비자도 구독자별 스레드로 격리하고, redrive는 실패한 구독자에게만 간다."""
    config = make_config(RetryPolicy())
    topic = SyncIsolatedEvent(value="probe").event_name
    calls: Counter[str] = Counter()
    gateway_up = threading.Event()

    def charge(event: SyncIsolatedEvent) -> None:
        calls["charge"] += 1
        if not gateway_up.is_set():
            raise RuntimeError(f"gateway down for {event.value}")

    def ship(event: SyncIsolatedEvent) -> None:
        calls["ship"] += 1

    consumer = KafkaEventConsumer(config)
    consumer.set_stop_event(threading.Event())
    consumer.register(
        SyncIsolatedEvent, charge, subscriber="billing", handler_name="charge"
    )
    consumer.register(
        SyncIsolatedEvent, ship, subscriber="shipping", handler_name="ship"
    )
    consumer.start()
    try:
        publish(
            config,
            [SyncIsolatedEvent(value="first"), SyncIsolatedEvent(value="second")],
        )

        records = read_records(config, f"{topic}.billing.dlt", 2)
        wait_until(lambda: calls["ship"] == 2)

        headers = decode_headers(records[0])
        assert headers[DeadLetterHeaderKey.CONSUMER_GROUP] == (
            f"{config.group_id}.billing"
        )
        assert DeadLetter.from_headers(headers).pending == frozenset({"charge"})
        assert end_offset(config, f"{topic}.shipping.dlt") == 0
        assert calls == {"charge": 2, "ship": 2}

        gateway_up.set()
        result = consumer.redrive(SyncIsolatedEvent, subscriber="billing")

        assert result == RedriveResult(succeeded=2, failed=0)
        assert calls == {"charge": 4, "ship": 2}
        assert consumer.redrive(SyncIsolatedEvent, subscriber="billing") == (
            RedriveResult(succeeded=0, failed=0)
        )
    finally:
        consumer.stop()


def test_sync_blocking_retry_expect_only_failed_handler_reruns_in_order() -> None:
    """동기 소비자의 제자리 재시도는 순서를 지키며 실패한 핸들러만 다시 실행한다."""
    config = make_config(RetryPolicy(max_attempts=3, initial_interval=0.1))
    topic = SyncRetryEvent(value="probe").event_name
    calls: Counter[str] = Counter()
    order: list[str] = []

    def flaky(event: SyncRetryEvent) -> None:
        calls["flaky"] += 1
        if event.value == "first" and calls["flaky"] < 3:
            raise RuntimeError("fails twice")
        order.append(event.value)

    def steady(event: SyncRetryEvent) -> None:
        calls[f"steady:{event.value}"] += 1

    consumer = KafkaEventConsumer(config)
    consumer.set_stop_event(threading.Event())
    consumer.register(SyncRetryEvent, flaky, handler_name="flaky")
    consumer.register(SyncRetryEvent, steady, handler_name="steady")
    consumer.start()
    try:
        publish(config, [SyncRetryEvent(value="first"), SyncRetryEvent(value="second")])

        wait_until(lambda: committed_offset(config, config.group_id, topic) == 2)

        assert calls == {"flaky": 4, "steady:first": 1, "steady:second": 1}
        assert order == ["first", "second"]
        assert end_offset(config, f"{topic}.dlt") == 0
    finally:
        consumer.stop()


async def test_delayed_retry_restart_with_latest_reset_expect_waiting_retry_delivered() -> (
    None
):
    """`auto_offset_reset=latest`여도 재시작 전에 쌓인 retry 레코드는 건너뛰지 않고 전달한다."""
    config = make_config(
        RetryPolicy(max_attempts=3, initial_interval=1.0, mode=RetryMode.DELAYED)
    )
    config.auto_offset_reset = AutoOffsetResetType.LATEST
    topic = RestartedRetryEvent(value="probe").event_name
    retry_topic = f"{topic}.retry"
    admin = AdminClient(config.connection_configuration_dict)
    for future in admin.create_topics(
        [NewTopic(name, 1, 1) for name in (topic, retry_topic, f"{topic}.dlt")]
    ).values():
        await asyncio.to_thread(future.result, MAX_WAIT_TIME)
    # 이벤트 토픽은 커밋된 위치에서 읽게 해, reset 정책이 retry 토픽에만 걸리게 한다.
    seed = Consumer(config.consumer_configuration_dict)
    try:
        seed.commit(offsets=[TopicPartition(topic, 0, 0)], asynchronous=False)
    finally:
        seed.close()
    calls: Counter[str] = Counter()

    async def flaky(event: RestartedRetryEvent) -> None:
        calls["flaky"] += 1
        if calls["flaky"] == 1:
            raise RuntimeError("first attempt fails")

    def make_consumer() -> AsyncKafkaEventConsumer:
        consumer = AsyncKafkaEventConsumer(config)
        consumer.set_stop_event(asyncio.Event())
        consumer.register(RestartedRetryEvent, flaky, handler_name="flaky")
        return consumer

    publish(config, [RestartedRetryEvent(value="only")])
    before_restart = make_consumer()
    await before_restart.start_async()
    try:

        async def retry_published() -> bool:
            return await asyncio.to_thread(end_offset, config, retry_topic) == 1

        await eventually(retry_published)
    finally:
        await before_restart.stop_async()
    assert calls == {"flaky": 1}
    assert (
        await asyncio.to_thread(committed_offset, config, config.group_id, retry_topic)
        < 0
    )

    after_restart = make_consumer()
    await after_restart.start_async()
    try:
        await eventually(lambda: calls["flaky"] == 2)

        async def retry_committed() -> bool:
            return (
                await asyncio.to_thread(
                    committed_offset, config, config.group_id, retry_topic
                )
                == 1
            )

        await eventually(retry_committed)
    finally:
        await after_restart.stop_async()
    assert await asyncio.to_thread(end_offset, config, f"{topic}.dlt") == 0
