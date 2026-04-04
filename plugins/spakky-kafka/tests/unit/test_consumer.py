"""Unit tests for Kafka event consumers.

Tests registration, routing, initialization, and lifecycle methods
for both synchronous and asynchronous Kafka event consumers.
"""

import threading
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
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


@patch("spakky.plugins.kafka.event.consumer.Consumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
def test_sync_consumer_initialize_expect_subscribe(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 initialize가 토픽 생성 및 구독을 수행하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_inner_consumer = MagicMock()
    mock_consumer_cls.return_value = mock_inner_consumer

    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())

    consumer.initialize()

    mock_inner_consumer.subscribe.assert_called_once_with(topics=["SampleEvent"])


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
def test_sync_consumer_dispose_expect_close(
    mock_admin_cls: MagicMock,
    mock_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 consumer의 dispose가 consumer.close()를 호출하는지 검증한다."""
    mock_inner_consumer = MagicMock()
    mock_consumer_cls.return_value = mock_inner_consumer

    consumer = KafkaEventConsumer(config)
    consumer.dispose()

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
@patch("spakky.plugins.kafka.event.consumer.AIOConsumer")
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_initialize_async_expect_subscribe(
    mock_admin_cls: MagicMock,
    mock_aio_consumer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 initialize_async가 토픽 생성 및 구독을 수행하는지 검증한다."""
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
@patch("spakky.plugins.kafka.event.consumer.AdminClient")
async def test_async_consumer_dispose_async_expect_close(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer의 dispose_async가 consumer.close()를 호출하는지 검증한다."""
    mock_aio_consumer = AsyncMock()

    consumer = AsyncKafkaEventConsumer(config)
    consumer.consumer = mock_aio_consumer

    await consumer.dispose_async()

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
    consumer.set_propagator(W3CTracePropagator())

    def raising_handler(event: SampleEvent) -> None:
        raise RuntimeError("handler error")

    consumer.register(SampleEvent, raising_handler)

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
async def test_async_consumer_route_handler_exception_expect_trace_context_cleared(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 consumer에서 핸들러 예외 시에도 TraceContext가 정리됨을 검증한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_propagator(W3CTracePropagator())

    async def raising_handler(event: SampleEvent) -> None:
        raise RuntimeError("handler error")

    consumer.register(SampleEvent, raising_handler)

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
