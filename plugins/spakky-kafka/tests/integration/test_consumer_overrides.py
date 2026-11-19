"""Real broker scenarios of consumer settings added through deployment overrides."""

import asyncio
from collections.abc import Callable
from time import monotonic
from typing import override
from uuid import uuid4

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient
from pydantic import TypeAdapter
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.delivery import RetryPolicy

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.consumer import AsyncKafkaEventConsumer

MAX_WAIT_TIME = 30
"""Diagnostic deadline in seconds for one broker observation."""

POLL_INTERVAL = 0.05
"""Seconds between two checks of a broker observation."""

ADMIN_REQUEST_TIMEOUT = 10.0
"""Seconds one admin request may take before the observation fails."""

LONG_POLL_INTERVAL_MS = 900000
"""A `max.poll.interval.ms` far above the librdkafka default of 300000."""

RUN_ID = uuid4().hex
"""Keeps topics and groups of this run apart from earlier runs on a reused broker."""


@immutable
class OverriddenEvent(AbstractIntegrationEvent):
    """Event read by one subscriber with its own client id and one without."""

    value: str

    @property
    @override
    def event_name(self) -> str:
        return f"test.consumer.overrides.{RUN_ID}"


def member_client_ids(config: KafkaConnectionConfig, group_id: str) -> list[str]:
    """Return the client ids the broker reports for the members of one group."""
    admin = AdminClient(config.connection_configuration_dict)
    description = admin.describe_consumer_groups([group_id])[group_id].result(
        timeout=ADMIN_REQUEST_TIMEOUT
    )
    return [member.client_id for member in description.members]


async def eventually(predicate: Callable[[], bool]) -> None:
    """Wait until a broker observation holds, failing after a diagnostic deadline."""
    deadline = monotonic() + MAX_WAIT_TIME
    while not await asyncio.to_thread(predicate):
        if monotonic() > deadline:
            raise TimeoutError("Observation did not hold before the deadline")
        await asyncio.sleep(POLL_INTERVAL)


async def test_consumer_overrides_expect_reach_real_subscriber_consumers() -> None:
    """공통·구독자 override가 실제 consumer에 실려 broker가 구독자별 client id를 본다."""
    config = KafkaConnectionConfig()
    config.group_id = f"overrides-{uuid4().hex}"
    config.retry = RetryPolicy()
    config.consumer_overrides = {"max.poll.interval.ms": LONG_POLL_INTERVAL_MS}
    config.subscriber_consumer_overrides = {
        "report-builder": {"client.id": "report-builder-client"}
    }
    received: dict[str, list[str]] = {"report-builder": [], "billing": []}

    async def build(event: OverriddenEvent) -> None:
        received["report-builder"].append(event.value)

    async def bill(event: OverriddenEvent) -> None:
        received["billing"].append(event.value)

    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    consumer.register(
        OverriddenEvent, build, subscriber="report-builder", handler_name="build"
    )
    consumer.register(OverriddenEvent, bill, subscriber="billing", handler_name="bill")
    await consumer.start_async()
    try:
        producer = Producer(config.producer_configuration_dict)
        event = OverriddenEvent(value="probe")
        producer.produce(
            event.event_name, value=TypeAdapter(OverriddenEvent).dump_json(event)
        )
        producer.flush(ADMIN_REQUEST_TIMEOUT)

        await eventually(
            lambda: received == {"report-builder": ["probe"], "billing": ["probe"]}
        )
        assert member_client_ids(config, f"{config.group_id}.report-builder") == [
            "report-builder-client"
        ]
        assert member_client_ids(config, f"{config.group_id}.billing") == [
            config.client_id
        ]
    finally:
        await consumer.stop_async()
