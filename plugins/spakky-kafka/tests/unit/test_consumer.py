"""Unit tests for Kafka event consumers.

Tests registration, routing, initialization, and lifecycle methods
for both synchronous and asynchronous Kafka event consumers.
"""

import logging
import threading
from asyncio import sleep
from typing import Any, override
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.errors import KafkaTimeoutError
from confluent_kafka import KafkaError, KafkaException
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_HEADER_KEY,
    AuthRequirementDeniedError,
    AuthVerificationProviderUnavailableError,
)
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.common.constants import DeadLetterHeaderKey
from spakky.plugins.kafka.event.consumer import (
    AsyncKafkaEventConsumer,
    KafkaEventConsumer,
)


@immutable
class SampleEvent(AbstractIntegrationEvent):
    """Test integration event."""

    data: str


@immutable
class AnotherEvent(AbstractIntegrationEvent):
    """Another test integration event."""

    value: int


@immutable
class RenamedEvent(AbstractIntegrationEvent):
    """Integration event with custom outbound topic identity."""

    data: str

    @property
    @override
    def event_name(self) -> str:
        return "external.renamed.v1"


@pytest.fixture(name="config")
def config_fixture() -> Generator[KafkaConnectionConfig, Any, None]:
    """Create a test Kafka configuration."""
    from os import environ

    from spakky.plugins.kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX

    env_vars = {
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID": "test-group",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID": "test-client",
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS": "localhost:9092",
    }
    original = {k: environ.get(k) for k in env_vars}
    for key, value in env_vars.items():
        environ[key] = value
    try:
        yield KafkaConnectionConfig()
    finally:
        for key, value in original.items():
            if value is None:
                environ.pop(key, None)
            else:
                environ[key] = value


SAMPLE_TIMESTAMP = (1, 1700000000000)
"""Kafka `(timestamp_type, timestamp)` pair returned by `Message.timestamp()`."""


@pytest.fixture(name="incoming_message")
def incoming_message_fixture() -> MagicMock:
    """Kafka 메시지 stub — 유효한 SampleEvent 본문과 원본 좌표를 담는다."""
    message = MagicMock()
    message.error.return_value = None
    message.topic.return_value = "SampleEvent"
    message.partition.return_value = 3
    message.offset.return_value = 42
    message.timestamp.return_value = SAMPLE_TIMESTAMP
    message.key.return_value = b"order-1"
    message.value.return_value = b'{"data": "hello"}'
    message.headers.return_value = [("traceparent", SAMPLE_TRACEPARENT.encode())]
    return message


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_init_expect_success(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 KafkaEventConsumer가 올바르게 초기화되는지 검증한다."""
    consumer = KafkaEventConsumer(config)

    assert consumer.config is config
    assert consumer.type_lookup == {}
    assert consumer.type_adapters == {}
    assert consumer.handlers == {}
    mock_admin_cls.assert_called_once_with(config.configuration_dict)
    mock_consumer_cls.assert_called_once()


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_register_expect_handler_stored(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 register가 핸들러를 올바르게 저장하는지 검증한다."""
    consumer = KafkaEventConsumer(config)
    handler = MagicMock()

    consumer.register(SampleEvent, handler)

    assert SampleEvent in consumer.handlers
    assert handler in consumer.handlers[SampleEvent]
    assert consumer.type_lookup["SampleEvent"] is SampleEvent
    assert SampleEvent in consumer.type_adapters


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_register_custom_event_name_expect_topic_lookup(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Custom event_name 등록은 class name 대신 outbound topic과 일치한다."""
    consumer = KafkaEventConsumer(config)
    handler = MagicMock()

    consumer.register(RenamedEvent, handler)

    assert consumer.type_lookup["external.renamed.v1"] is RenamedEvent
    assert "RenamedEvent" not in consumer.type_lookup


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_register_multiple_handlers_expect_all_stored(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer에 동일 이벤트에 복수 핸들러 등록이 가능한지 검증한다."""
    consumer = KafkaEventConsumer(config)
    handler1 = MagicMock()
    handler2 = MagicMock()

    consumer.register(SampleEvent, handler1)
    consumer.register(SampleEvent, handler2)

    assert len(consumer.handlers[SampleEvent]) == 2


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_create_topics_expect_topics_created(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 _create_topics가 존재하지 않는 토픽을 생성하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    consumer = KafkaEventConsumer(config)
    consumer._create_topics(["topic1", "topic2"])

    mock_admin.create_topics.assert_called_once()
    new_topics = mock_admin.create_topics.call_args[0][0]
    topic_names = {t.topic for t in new_topics}
    assert topic_names == {"topic1", "topic2"}


@patch("spakky.plugins.kafka.event.consumer.Producer")
@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_initialize_expect_subscribe(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 initialize가 토픽 생성 및 구독을 수행하는지 검증한다."""
    del mock_producer_cls
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_inner_consumer = MagicMock()
    mock_consumer_cls.return_value = mock_inner_consumer

    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())

    consumer.initialize()

    mock_inner_consumer.subscribe.assert_called_once_with(topics=["SampleEvent"])


@patch("spakky.plugins.kafka.event.consumer.Producer")
@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_initialize_expect_dead_letter_topic_created(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """initialize가 구독 토픽과 함께 dead-letter 토픽도 생성한다."""
    del mock_consumer_cls, mock_producer_cls
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())

    consumer.initialize()

    created_topics = {topic.topic for topic in mock_admin.create_topics.call_args[0][0]}
    assert created_topics == {"SampleEvent", "SampleEvent.dlt"}


@patch("spakky.plugins.kafka.event.consumer.Producer")
@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_initialize_custom_event_name_expect_subscribe_to_event_name(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Custom event_name topic을 생성하고 구독한다."""
    del mock_producer_cls
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_inner_consumer = MagicMock()
    mock_consumer_cls.return_value = mock_inner_consumer

    consumer = KafkaEventConsumer(config)
    consumer.register(RenamedEvent, MagicMock())

    consumer.initialize()

    mock_inner_consumer.subscribe.assert_called_once_with(
        topics=["external.renamed.v1"]
    )


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_event_handler_expect_handler_called(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 _route_event_handler가 메시지를 핸들러로 라우팅하는지 검증한다."""
    consumer = KafkaEventConsumer(config)
    handler = MagicMock()
    consumer.register(SampleEvent, handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "hello"}'

    consumer._route_event_handler(mock_message)

    handler.assert_called_once()
    event_arg = handler.call_args[0][0]
    assert event_arg.data == "hello"


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_custom_event_name_expect_handler_called(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Custom event_name topic 수신이 class name mismatch 없이 handler로 라우팅된다."""
    consumer = KafkaEventConsumer(config)
    handler = MagicMock()
    consumer.register(RenamedEvent, handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "external.renamed.v1"
    mock_message.value.return_value = b'{"data": "hello"}'

    consumer._route_event_handler(mock_message)

    handler.assert_called_once()
    event_arg = handler.call_args[0][0]
    assert event_arg.data == "hello"


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_multiple_handlers_expect_all_called(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer가 복수 핸들러 모두 호출하는지 검증한다."""
    consumer = KafkaEventConsumer(config)
    handler1 = MagicMock()
    handler2 = MagicMock()
    consumer.register(SampleEvent, handler1)
    consumer.register(SampleEvent, handler2)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "hello"}'

    consumer._route_event_handler(mock_message)

    handler1.assert_called_once()
    handler2.assert_called_once()


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_auth_boundary_handler_receives_headers(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Auth-aware post-processor endpoints receive Kafka headers from consumer."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    captured_headers: list[dict[str, str] | None] = []

    def handler(
        event: SampleEvent,
        _spakky_kafka_headers: dict[str, str] | None = None,
    ) -> None:
        del event
        captured_headers.append(_spakky_kafka_headers)

    consumer.register(SampleEvent, handler)
    consumer.register_auth_boundary(handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "hello"}'
    mock_message.headers.return_value = [
        (AUTH_CONTEXT_SNAPSHOT_HEADER_KEY, b"snapshot-envelope"),
    ]

    consumer._route_event_handler(mock_message)

    assert captured_headers == [{AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "snapshot-envelope"}]


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_auth_deny_is_handled_without_retry(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """DENY-style auth failures do not escape the route handler."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = MagicMock()

    def handler(event: SampleEvent) -> None:
        del event
        raise AuthRequirementDeniedError()

    consumer.register(SampleEvent, handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "hello"}'
    mock_message.headers.return_value = []

    consumer._route_event_handler(mock_message)

    consumer.producer.produce.assert_not_called()


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_provider_unavailable_is_retryable(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Provider unavailable ERROR propagates instead of being logged and advanced."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)

    def handler(event: SampleEvent) -> None:
        del event
        raise AuthVerificationProviderUnavailableError()

    consumer.register(SampleEvent, handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "hello"}'
    mock_message.headers.return_value = []

    with pytest.raises(AuthVerificationProviderUnavailableError):
        consumer._route_event_handler(mock_message)


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_run_expect_poll_and_route(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 run이 poll 후 이벤트를 라우팅하는지 검증한다."""
    mock_inner_consumer = MagicMock()
    mock_consumer_cls.return_value = mock_inner_consumer

    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())

    stop_event = threading.Event()
    consumer._stop_event = stop_event

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'

    # poll returns message first, then None, then triggers stop
    call_count = 0

    def poll_side_effect(timeout: float) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None  # skip
        if call_count == 2:
            return mock_message
        stop_event.set()
        return None

    mock_inner_consumer.poll.side_effect = poll_side_effect

    consumer.run()

    assert call_count == 3


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_dispose_expect_producer_flushed_and_consumer_closed(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 dispose가 미발행 dead-letter를 flush하고 consumer를 닫는지 검증한다."""
    mock_inner_consumer = MagicMock()
    mock_consumer_cls.return_value = mock_inner_consumer

    consumer = KafkaEventConsumer(config)
    consumer.producer = MagicMock()

    consumer.dispose()

    consumer.producer.flush.assert_called_once_with(config.dead_letter_delivery_timeout)
    mock_inner_consumer.close.assert_called_once()


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_init_expect_success(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 AsyncKafkaEventConsumer가 올바르게 초기화되는지 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)

    assert consumer.config is config
    assert consumer.type_lookup == {}
    assert consumer.type_adapters == {}
    assert consumer.handlers == {}
    mock_admin_cls.assert_called_once_with(config.configuration_dict)


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_register_expect_handler_stored(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 register가 핸들러를 올바르게 저장하는지 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    handler = AsyncMock()

    consumer.register(SampleEvent, handler)

    assert SampleEvent in consumer.handlers
    assert handler in consumer.handlers[SampleEvent]
    assert consumer.type_lookup["SampleEvent"] is SampleEvent
    assert SampleEvent in consumer.type_adapters


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_register_custom_event_name_expect_topic_lookup(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Async custom event_name 등록도 outbound topic identity를 사용한다."""
    consumer = AsyncKafkaEventConsumer(config)
    handler = AsyncMock()

    consumer.register(RenamedEvent, handler)

    assert consumer.type_lookup["external.renamed.v1"] is RenamedEvent
    assert "RenamedEvent" not in consumer.type_lookup


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_register_multiple_handlers_expect_all_stored(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에 동일 이벤트에 복수 핸들러 등록이 가능한지 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    handler1 = AsyncMock()
    handler2 = AsyncMock()

    consumer.register(SampleEvent, handler1)
    consumer.register(SampleEvent, handler2)

    assert len(consumer.handlers[SampleEvent]) == 2


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_register_auth_boundary_expect_handler_marked(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Async consumer records auth-aware endpoints for header delivery."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    handler = AsyncMock()

    consumer.register(SampleEvent, handler)
    consumer.register_auth_boundary(handler)

    assert handler in consumer._auth_boundary_handlers


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_auth_boundary_handler_receives_headers(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """Auth-aware async endpoints receive Kafka headers from consumer."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    captured_headers: list[dict[str, str] | None] = []

    async def handler(
        event: SampleEvent,
        _spakky_kafka_headers: dict[str, str] | None = None,
    ) -> None:
        del event
        captured_headers.append(_spakky_kafka_headers)

    consumer.register(SampleEvent, handler)
    consumer.register_auth_boundary(handler)
    incoming_message.headers.return_value = [
        (AUTH_CONTEXT_SNAPSHOT_HEADER_KEY, b"snapshot-envelope"),
    ]

    await consumer._route_event_handler(incoming_message)

    assert captured_headers == [{AUTH_CONTEXT_SNAPSHOT_HEADER_KEY: "snapshot-envelope"}]


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_create_topics_expect_topics_created(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 _create_topics가 존재하지 않는 토픽을 생성하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    consumer = AsyncKafkaEventConsumer(config)
    consumer._create_topics(["topic1"])

    mock_admin.create_topics.assert_called_once()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.consumer.AIOConsumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_initialize_async_expect_subscribe(
    mock_admin_cls: MagicMock,
    mock_aio_consumer_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 initialize_async가 토픽 생성 및 구독을 수행하는지 검증한다."""
    mock_aio_producer_cls.return_value = AsyncMock()
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer_cls.return_value = mock_aio_consumer

    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())

    await consumer.initialize_async()

    mock_aio_consumer.subscribe.assert_awaited_once_with(topics=["SampleEvent"])


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.consumer.AIOConsumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_initialize_async_expect_dead_letter_topic_created(
    mock_admin_cls: MagicMock,
    mock_aio_consumer_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """initialize_async가 구독 토픽과 함께 dead-letter 토픽도 생성한다."""
    mock_aio_producer_cls.return_value = AsyncMock()
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin
    mock_aio_consumer_cls.return_value = AsyncMock()

    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())

    await consumer.initialize_async()

    created_topics = {topic.topic for topic in mock_admin.create_topics.call_args[0][0]}
    assert created_topics == {"SampleEvent", "SampleEvent.dlt"}


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.consumer.AIOConsumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_initialize_custom_event_name_expect_subscribe_to_event_name(
    mock_admin_cls: MagicMock,
    mock_aio_consumer_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """Async consumer도 custom event_name topic을 생성하고 구독한다."""
    mock_aio_producer_cls.return_value = AsyncMock()
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer_cls.return_value = mock_aio_consumer

    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(RenamedEvent, AsyncMock())

    await consumer.initialize_async()

    mock_aio_consumer.subscribe.assert_awaited_once_with(topics=["external.renamed.v1"])


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_dispose_async_expect_producer_and_consumer_closed(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 dispose_async가 dead-letter producer와 consumer를 모두 닫는지 검증한다."""
    mock_aio_consumer = AsyncMock()
    mock_aio_producer = AsyncMock()

    consumer = AsyncKafkaEventConsumer(config)
    consumer.consumer = mock_aio_consumer
    consumer.producer = mock_aio_producer

    await consumer.dispose_async()

    mock_aio_producer.stop.assert_awaited_once()
    mock_aio_consumer.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Trace context extraction tests
# ---------------------------------------------------------------------------

SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_with_traceparent_expect_child_context_set(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """traceparent 헤더가 있으면 child TraceContext가 활성화됨을 검증한다."""
    consumer = KafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    captured_ctx: list[TraceContext | None] = []

    def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    consumer._route_event_handler(mock_message)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx is not None
    assert ctx.trace_id == SAMPLE_TRACE_ID
    assert ctx.parent_span_id == SAMPLE_SPAN_ID
    assert ctx.span_id != SAMPLE_SPAN_ID


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_with_traceparent_expect_child_context_set(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 traceparent 헤더가 있으면 child TraceContext가 활성화됨을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    captured_ctx: list[TraceContext | None] = []

    async def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    await consumer._route_event_handler(mock_message)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx is not None
    assert ctx.trace_id == SAMPLE_TRACE_ID
    assert ctx.parent_span_id == SAMPLE_SPAN_ID
    assert ctx.span_id != SAMPLE_SPAN_ID


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_without_propagator_expect_no_trace_context(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """propagator 미설정 시 TraceContext가 설정되지 않음을 검증한다."""
    consumer = KafkaEventConsumer(config)

    captured_ctx: list[TraceContext | None] = []

    def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    TraceContext.clear()
    consumer._route_event_handler(mock_message)

    assert captured_ctx[0] is None


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_without_propagator_expect_no_trace_context(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 propagator 미설정 시 TraceContext가 설정되지 않음을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)

    captured_ctx: list[TraceContext | None] = []

    async def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    TraceContext.clear()
    await consumer._route_event_handler(mock_message)

    assert captured_ctx[0] is None


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_with_none_headers_expect_new_root_trace(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """headers가 None이면 new root TraceContext가 생성됨을 검증한다."""
    consumer = KafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    captured_ctx: list[TraceContext | None] = []

    def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = None

    consumer._route_event_handler(mock_message)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx is not None
    assert ctx.parent_span_id is None


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_with_none_headers_expect_new_root_trace(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 headers가 None이면 new root TraceContext가 생성됨을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    captured_ctx: list[TraceContext | None] = []

    async def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = None

    await consumer._route_event_handler(mock_message)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx is not None
    assert ctx.parent_span_id is None


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_with_empty_headers_expect_new_root_trace(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """headers가 빈 리스트이면 new root TraceContext가 생성됨을 검증한다."""
    consumer = KafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    captured_ctx: list[TraceContext | None] = []

    def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = []

    consumer._route_event_handler(mock_message)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx is not None
    assert ctx.parent_span_id is None


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_with_empty_headers_expect_new_root_trace(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 headers가 빈 리스트이면 new root TraceContext가 생성됨을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    captured_ctx: list[TraceContext | None] = []

    async def capturing_handler(event: SampleEvent) -> None:
        captured_ctx.append(TraceContext.get())

    consumer.register(SampleEvent, capturing_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = []

    await consumer._route_event_handler(mock_message)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx is not None
    assert ctx.parent_span_id is None


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_trace_context_cleared_after_handler(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """핸들러 완료 후 TraceContext가 정리됨을 검증한다."""
    consumer = KafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())
    consumer.register(SampleEvent, MagicMock())

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    consumer._route_event_handler(mock_message)

    assert TraceContext.get() is None


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_trace_context_cleared_after_handler(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 핸들러 완료 후 TraceContext가 정리됨을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())
    consumer.register(SampleEvent, AsyncMock())

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    await consumer._route_event_handler(mock_message)

    assert TraceContext.get() is None


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_handler_exception_expect_trace_context_cleared(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """핸들러 예외 시에도 TraceContext가 정리됨을 검증한다."""
    consumer = KafkaEventConsumer(config)
    consumer.producer = MagicMock()
    consumer.set_propagator(W3CTracePropagator())

    def raising_handler(event: SampleEvent) -> None:
        raise RuntimeError("handler error")

    consumer.register(SampleEvent, raising_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.timestamp.return_value = SAMPLE_TIMESTAMP
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    consumer._route_event_handler(mock_message)

    assert TraceContext.get() is None


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_handler_exception_expect_trace_context_cleared(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 핸들러 예외 시에도 TraceContext가 정리됨을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()
    consumer.set_propagator(W3CTracePropagator())

    async def raising_handler(event: SampleEvent) -> None:
        raise RuntimeError("handler error")

    consumer.register(SampleEvent, raising_handler)

    mock_message = MagicMock()
    mock_message.error.return_value = None
    mock_message.topic.return_value = "SampleEvent"
    mock_message.value.return_value = b'{"data": "test"}'
    mock_message.timestamp.return_value = SAMPLE_TIMESTAMP
    mock_message.headers.return_value = [
        ("traceparent", SAMPLE_TRACEPARENT.encode()),
    ]

    await consumer._route_event_handler(mock_message)

    assert TraceContext.get() is None


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_to_string_headers_with_bytes_expect_decoded(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """_to_string_headers가 bytes 값을 문자열로 디코딩하는지 검증한다."""
    consumer = KafkaEventConsumer(config)

    result = consumer._to_string_headers(
        [
            ("traceparent", b"00-abc-def-01"),
            ("custom", b"value"),
        ]
    )

    assert result == {"traceparent": "00-abc-def-01", "custom": "value"}


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_to_string_headers_with_mixed_values_expect_str_and_bytes_kept(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """_to_string_headers가 str, bytes, None 혼합 값을 올바르게 처리하는지 검증한다."""
    consumer = KafkaEventConsumer(config)

    result = consumer._to_string_headers(
        [
            ("str-header", "already-string"),
            ("bytes-header", b"needs-decode"),
            ("none-header", None),
        ]
    )

    assert result == {"str-header": "already-string", "bytes-header": "needs-decode"}


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_to_string_headers_with_none_expect_empty(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """_to_string_headers가 None 입력에 빈 dict를 반환하는지 검증한다."""
    consumer = KafkaEventConsumer(config)

    result = consumer._to_string_headers(None)

    assert result == {}


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_to_string_headers_with_bytes_expect_decoded(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 _to_string_headers가 bytes 값을 문자열로 디코딩하는지 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)

    result = consumer._to_string_headers(
        [
            ("traceparent", b"00-abc-def-01"),
            ("custom", b"value"),
        ]
    )

    assert result == {"traceparent": "00-abc-def-01", "custom": "value"}


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_to_string_headers_with_mixed_values_expect_str_and_bytes_kept(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 _to_string_headers가 str, bytes, None 혼합 값을 올바르게 처리하는지 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)

    result = consumer._to_string_headers(
        [
            ("str-header", "already-string"),
            ("bytes-header", b"needs-decode"),
            ("none-header", None),
        ]
    )

    assert result == {"str-header": "already-string", "bytes-header": "needs-decode"}


@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_async_consumer_to_string_headers_with_none_expect_empty(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 _to_string_headers가 None 입력에 빈 dict를 반환하는지 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)

    result = consumer._to_string_headers(None)

    assert result == {}


# ---------------------------------------------------------------------------
# Dead-letter routing tests
# ---------------------------------------------------------------------------


EXPECTED_DEAD_LETTER_HEADERS = {
    "traceparent": SAMPLE_TRACEPARENT,
    DeadLetterHeaderKey.ORIGINAL_TOPIC: "SampleEvent",
    DeadLetterHeaderKey.ORIGINAL_PARTITION: "3",
    DeadLetterHeaderKey.ORIGINAL_OFFSET: "42",
    DeadLetterHeaderKey.ORIGINAL_TIMESTAMP: "1700000000000",
    DeadLetterHeaderKey.CONSUMER_GROUP: "test-group",
    DeadLetterHeaderKey.EXCEPTION_TYPE: "RuntimeError",
    DeadLetterHeaderKey.EXCEPTION_MESSAGE: "handler exploded",
}
"""Headers a reprocessing tool must find on a message that failed in `failing_handler`."""


def failing_handler(event: SampleEvent) -> None:
    """Handler that always fails, driving the message onto the dead-letter topic."""
    del event
    raise RuntimeError("handler exploded")


async def async_failing_handler(event: SampleEvent) -> None:
    """Async counterpart of `failing_handler`."""
    del event
    raise RuntimeError("handler exploded")


def delivering_producer() -> MagicMock:
    """Sync producer stub whose flush reports every record as delivered."""
    producer = MagicMock()
    producer.flush.return_value = 0
    return producer


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_undeserializable_message_expect_dead_letter_without_handler_call(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """역직렬화되지 않는 메시지는 핸들러를 호출하지 않고 즉시 dead-letter로 보낸다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = delivering_producer()
    handler = MagicMock()
    consumer.register(SampleEvent, handler)
    incoming_message.value.return_value = b"not-an-event"

    consumer._route_event_handler(incoming_message)

    handler.assert_not_called()
    produced = consumer.producer.produce.call_args.kwargs
    assert produced["topic"] == "SampleEvent.dlt"
    assert produced["value"] == b"not-an-event"
    assert produced["headers"][DeadLetterHeaderKey.EXCEPTION_TYPE] == "ValidationError"


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_failing_handler_expect_dead_letter_with_origin_headers(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """핸들러가 실패하면 원본 좌표와 예외 정보를 헤더에 실어 dead-letter로 보낸다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = delivering_producer()
    consumer.register(SampleEvent, failing_handler)

    consumer._route_event_handler(incoming_message)

    produced = consumer.producer.produce.call_args.kwargs
    assert produced["topic"] == "SampleEvent.dlt"
    assert produced["value"] == b'{"data": "hello"}'
    assert produced["key"] == b"order-1"
    assert produced["headers"] == EXPECTED_DEAD_LETTER_HEADERS


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_failing_handler_expect_bounded_delivery_wait(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """dead-letter 발행은 delivery report를 걸고 설정된 시간까지만 배달을 기다린다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = delivering_producer()
    consumer.register(SampleEvent, failing_handler)

    consumer._route_event_handler(incoming_message)

    assert (
        consumer.producer.produce.call_args.kwargs["callback"]
        == consumer._dead_letter_delivery_report
    )
    consumer.producer.flush.assert_called_once_with(config.dead_letter_delivery_timeout)


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_undelivered_dead_letter_expect_error_logged(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """배달 시간 안에 나가지 못한 dead-letter 레코드는 조용히 사라지지 않고 기록된다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = MagicMock()
    consumer.producer.flush.return_value = 1
    consumer.register(SampleEvent, failing_handler)

    with caplog.at_level(logging.ERROR):
        consumer._route_event_handler(incoming_message)

    assert "still unsent" in caplog.text


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_delivery_report_with_broker_error_expect_error_logged(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """브로커가 dead-letter 레코드를 거절하면 delivery report가 실패를 기록한다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    rejected = MagicMock()
    rejected.topic.return_value = "SampleEvent.dlt"

    with caplog.at_level(logging.ERROR):
        consumer._dead_letter_delivery_report(
            KafkaError(KafkaError._MSG_TIMED_OUT), rejected
        )

    assert "Dead-letter delivery failed for SampleEvent.dlt" in caplog.text


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_delivery_report_without_error_expect_silence(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """정상 배달된 dead-letter 레코드는 오류로 기록되지 않는다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)

    with caplog.at_level(logging.ERROR):
        consumer._dead_letter_delivery_report(None, MagicMock())

    assert caplog.text == ""


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_failing_handler_with_retries_expect_retried_before_dead_letter(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """max_handler_retries만큼 핸들러를 다시 호출한 뒤에야 dead-letter로 보낸다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config.model_copy(update={"max_handler_retries": 2}))
    consumer.producer = delivering_producer()
    attempts: list[SampleEvent] = []

    def counting_failing_handler(event: SampleEvent) -> None:
        attempts.append(event)
        raise RuntimeError("handler exploded")

    consumer.register(SampleEvent, counting_failing_handler)

    consumer._route_event_handler(incoming_message)

    assert len(attempts) == 3
    consumer.producer.produce.assert_called_once()


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_successful_handler_expect_no_dead_letter(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """핸들러가 성공한 메시지는 dead-letter로 보내지 않는다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = delivering_producer()
    consumer.register(SampleEvent, MagicMock())

    consumer._route_event_handler(incoming_message)

    consumer.producer.produce.assert_not_called()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_undeserializable_message_expect_dead_letter_without_handler_call(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """비동기 consumer도 역직렬화 실패 메시지를 핸들러 없이 dead-letter로 보낸다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()
    handler = AsyncMock()
    consumer.register(SampleEvent, handler)
    incoming_message.value.return_value = b"not-an-event"

    await consumer._route_event_handler(incoming_message)

    handler.assert_not_awaited()
    sent = consumer.producer.send_and_wait.call_args.kwargs
    assert sent["topic"] == "SampleEvent.dlt"
    assert sent["value"] == b"not-an-event"
    assert (
        dict(sent["headers"])[DeadLetterHeaderKey.EXCEPTION_TYPE] == b"ValidationError"
    )


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_failing_handler_expect_dead_letter_with_origin_headers(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """비동기 핸들러 실패도 원본 좌표와 예외 정보를 헤더에 실어 dead-letter로 보낸다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()
    consumer.register(SampleEvent, async_failing_handler)

    await consumer._route_event_handler(incoming_message)

    sent = consumer.producer.send_and_wait.call_args.kwargs
    assert sent["topic"] == "SampleEvent.dlt"
    assert sent["value"] == b'{"data": "hello"}'
    assert sent["key"] == b"order-1"
    assert {key: value.decode() for key, value in sent["headers"]} == (
        EXPECTED_DEAD_LETTER_HEADERS
    )


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_rejected_dead_letter_expect_error_logged(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """브로커가 비동기 dead-letter 발행을 거절해도 poll 루프를 죽이지 않고 기록한다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()
    consumer.producer.send_and_wait.side_effect = KafkaTimeoutError(
        "broker unreachable"
    )
    consumer.register(SampleEvent, async_failing_handler)

    with caplog.at_level(logging.ERROR):
        await consumer._route_event_handler(incoming_message)

    assert "Dead-letter delivery failed for SampleEvent" in caplog.text


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_failing_handler_with_retries_expect_retried_before_dead_letter(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """비동기 consumer도 max_handler_retries만큼 재호출한 뒤 dead-letter로 보낸다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(
        config.model_copy(update={"max_handler_retries": 2})
    )
    consumer.producer = AsyncMock()
    attempts: list[SampleEvent] = []

    async def counting_failing_handler(event: SampleEvent) -> None:
        attempts.append(event)
        raise RuntimeError("handler exploded")

    consumer.register(SampleEvent, counting_failing_handler)

    await consumer._route_event_handler(incoming_message)

    assert len(attempts) == 3
    consumer.producer.send_and_wait.assert_awaited_once()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_successful_handler_expect_no_dead_letter(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """비동기 핸들러가 성공한 메시지는 dead-letter로 보내지 않는다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()
    consumer.register(SampleEvent, AsyncMock())

    await consumer._route_event_handler(incoming_message)

    consumer.producer.send_and_wait.assert_not_awaited()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_auth_deny_expect_no_dead_letter(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """DENY 판정 메시지는 실패가 아니므로 dead-letter로 보내지 않는다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()

    async def denying_handler(event: SampleEvent) -> None:
        del event
        raise AuthRequirementDeniedError()

    consumer.register(SampleEvent, denying_handler)

    await consumer._route_event_handler(incoming_message)

    consumer.producer.send_and_wait.assert_not_awaited()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_provider_unavailable_expect_propagated(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
) -> None:
    """검증 provider 장애는 재시도 대상이므로 dead-letter 없이 그대로 전파된다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(config)
    consumer.producer = AsyncMock()

    async def unavailable_handler(event: SampleEvent) -> None:
        del event
        raise AuthVerificationProviderUnavailableError()

    consumer.register(SampleEvent, unavailable_handler)

    with pytest.raises(AuthVerificationProviderUnavailableError):
        await consumer._route_event_handler(incoming_message)

    consumer.producer.send_and_wait.assert_not_awaited()


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_rejected_dead_letter_expect_error_logged(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """produce가 레코드를 거절해도 poll 스레드를 죽이지 않고 기록한다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = delivering_producer()
    consumer.producer.produce.side_effect = KafkaException(
        KafkaError(KafkaError.MSG_SIZE_TOO_LARGE)
    )
    consumer.register(SampleEvent, failing_handler)

    with caplog.at_level(logging.ERROR):
        consumer._route_event_handler(incoming_message)

    assert "Dead-letter delivery failed for SampleEvent" in caplog.text
    consumer.producer.flush.assert_not_called()


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_route_full_producer_queue_expect_error_logged(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """로컬 큐가 가득 차 produce가 실패해도 poll 스레드를 죽이지 않고 기록한다."""
    del mock_admin_cls, mock_consumer_cls
    consumer = KafkaEventConsumer(config)
    consumer.producer = delivering_producer()
    consumer.producer.produce.side_effect = BufferError("queue full")
    consumer.register(SampleEvent, failing_handler)

    with caplog.at_level(logging.ERROR):
        consumer._route_event_handler(incoming_message)

    assert "Dead-letter delivery failed for SampleEvent" in caplog.text


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_route_unconfirmed_dead_letter_expect_duplicate_warning(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
    incoming_message: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """배달 확인이 시간 안에 오지 않으면 확정 실패와 구분해 중복 가능성을 알린다."""
    del mock_admin_cls
    consumer = AsyncKafkaEventConsumer(
        config.model_copy(update={"dead_letter_delivery_timeout": 0.01})
    )
    consumer.producer = AsyncMock()

    async def never_confirming_send(**kwargs: Any) -> None:
        del kwargs
        await sleep(3600)

    consumer.producer.send_and_wait.side_effect = never_confirming_send
    consumer.register(SampleEvent, async_failing_handler)

    with caplog.at_level(logging.ERROR):
        await consumer._route_event_handler(incoming_message)

    assert "unconfirmed after" in caplog.text
    assert "may still be delivered" in caplog.text
