"""Real broker deferral, reassignment and shutdown regression."""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import ClassVar, override
from uuid import uuid4

from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.aio import AIOConsumer
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event import EventDeferredError

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.consumer import AsyncKafkaEventConsumer


class ShortPollConfig(KafkaConnectionConfig):
    """Use a real short poll limit so a held gate exceeds it many times."""

    @property
    @override
    def consumer_configuration_dict(self) -> dict[str, str | int | float | bool]:
        return {
            **super().consumer_configuration_dict,
            "max.poll.interval.ms": 6000,
            "session.timeout.ms": 6000,
        }


class ObservedConsumer(AsyncKafkaEventConsumer):
    """Observe real rebalance callbacks without replacing native lifecycle."""

    rebalances: int = 0

    @override
    async def _clear_deferred(
        self, consumer: AIOConsumer, partitions: list[TopicPartition]
    ) -> None:
        self.rebalances += 1
        await super()._clear_deferred(consumer, partitions)


async def eventually(
    predicate: Callable[[], Awaitable[bool]], timeout: float = 30
) -> None:
    """Wait for a concrete broker observation, bounded by a diagnostic deadline."""
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(0.05)


async def test_native_deferral_beyond_poll_limit_expect_no_commit_and_restart_redelivery() -> (
    None
):
    """35초 fence·실제 재할당·종료 후에도 DLT 없이 원본 순서로 재전달한다."""
    topic = "test.deferral." + uuid4().hex

    @immutable
    class DeferredEvent(AbstractIntegrationEvent):
        value: str
        topic_name: ClassVar[str] = topic

        @property
        @override
        def event_name(self) -> str:
            return self.topic_name

    config = ShortPollConfig()
    config.group_id = "deferred-" + uuid4().hex
    config.number_of_partitions = 3
    config.poll_timeout = 0.05
    config.max_handler_retries = 0
    admin = AdminClient(config.connection_configuration_dict)
    for future in admin.create_topics(
        [NewTopic(topic, 3, 1), NewTopic(topic + ".dlt", 3, 1)]
    ).values():
        await asyncio.to_thread(future.result, 15)
    producer = Producer(config.producer_configuration_dict)
    inspector = Consumer(config.consumer_configuration_dict)
    release = asyncio.Event()
    attempted = asyncio.Event()
    effects: list[str] = []
    attempts: Counter[str] = Counter()

    async def handler(event: DeferredEvent) -> None:
        attempts[event.value] += 1
        if event.value != "independent" and not release.is_set():
            attempted.set()
            raise EventDeferredError(retry_after=10)
        effects.append(event.value)

    def make_consumer() -> ObservedConsumer:
        consumer = ObservedConsumer(config)
        consumer.set_stop_event(asyncio.Event())
        consumer.register(DeferredEvent, handler)
        return consumer

    async def publish(value: str, partition: int) -> None:
        producer.produce(
            topic,
            value=TypeAdapter(DeferredEvent).dump_json(DeferredEvent(value=value)),
            partition=partition,
        )
        assert await asyncio.to_thread(producer.flush, 10) == 0

    async def no_commit_or_dlt() -> None:
        committed = await asyncio.to_thread(
            inspector.committed, [TopicPartition(topic, 0)], 10
        )
        assert committed[0].offset < 0
        for partition in range(3):
            assert (
                await asyncio.to_thread(
                    inspector.get_watermark_offsets,
                    TopicPartition(topic + ".dlt", partition),
                    10,
                )
            )[1] == 0

    first = make_consumer()
    second = make_consumer()
    final = make_consumer()
    active: list[ObservedConsumer] = []
    try:
        await first.start_async()
        active.append(first)
        await publish("first", 0)
        await asyncio.wait_for(attempted.wait(), 30)
        await publish("second", 0)
        await publish("independent", 1)

        async def independent_done() -> bool:
            return effects == ["independent"]

        await eventually(independent_done)
        baseline_rebalances = first.rebalances
        # The gate remains closed for >5 times max.poll.interval.ms. No exact
        # timing threshold is used to infer group health: assignment and native
        # callback counts are checked below against actual broker state.
        try:
            await asyncio.wait_for(release.wait(), 35)
        except TimeoutError:
            assert not release.is_set()
        assert first.rebalances == baseline_rebalances
        assert len(await first.consumer.assignment()) == 3
        assert effects == ["independent"]
        assert attempts["first"] >= 3
        assert attempts["second"] == 0
        await no_commit_or_dlt()

        await second.start_async()
        active.append(second)

        async def both_assigned() -> bool:
            return bool(await first.consumer.assignment()) and bool(
                await second.consumer.assignment()
            )

        await eventually(both_assigned)
        assert first.rebalances > baseline_rebalances
        await no_commit_or_dlt()
        # Stop while still deferred, not after opening the gate. Native stop
        # must not wait for the retry deadline or application availability.
        started = monotonic()
        await asyncio.wait_for(
            asyncio.gather(first.stop_async(), second.stop_async()), 10
        )
        active.clear()
        assert monotonic() - started < 10
        await no_commit_or_dlt()

        release.set()
        await final.start_async()
        active.append(final)

        async def recovered() -> bool:
            return "second" in effects

        await eventually(recovered)
        assert effects == ["independent", "first", "second"]

        async def committed_after_effects() -> bool:
            positions = await asyncio.to_thread(
                inspector.committed, [TopicPartition(topic, 0)], 10
            )
            return positions[0].offset == 2

        await eventually(committed_after_effects)
    finally:
        for consumer in active:
            await asyncio.wait_for(consumer.stop_async(), 10)
        inspector.close()
        for future in admin.delete_topics([topic, topic + ".dlt"]).values():
            await asyncio.to_thread(future.result, 15)
