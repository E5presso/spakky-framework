"""Tests for RabbitMQ consumer error handling.

This module tests the edge cases in RabbitMQ event consumers,
particularly the InvalidMessageError conditions.
"""

from os import environ
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.error import InvalidMessageError

from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig
from spakky.plugins.rabbitmq.common.constants import RABBITMQ_CONFIG_ENV_PREFIX
from spakky.plugins.rabbitmq.event.consumer import (
    AsyncRabbitMQEventConsumer,
    RabbitMQEventConsumer,
)


class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Sample integration event for testing."""

    data: str


@pytest.fixture(name="config")
def config_fixture() -> Generator[RabbitMQConnectionConfig, Any, None]:
    """Create a test RabbitMQ configuration from environment variables."""
    env_vars = {
        f"{RABBITMQ_CONFIG_ENV_PREFIX}USE_SSL": "false",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}HOST": "localhost",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}PORT": "5672",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}USER": "guest",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}PASSWORD": "guest",
        f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME": "test_exchange",
    }
    original = {k: environ.get(k) for k in env_vars}
    for key, value in env_vars.items():
        environ[key] = value
    try:
        yield RabbitMQConnectionConfig()
    finally:
        for key, value in original.items():
            if value is None:
                environ.pop(key, None)
            else:
                environ[key] = value


def test_sync_consumer_route_event_handler_missing_consumer_tag_expect_error(
    config: RabbitMQConnectionConfig,
) -> None:
    """consumer_tag가 None일 때 InvalidMessageError가 발생함을 검증한다."""
    consumer = RabbitMQEventConsumer(config)
    consumer.register(SampleIntegrationEvent, MagicMock())

    channel = MagicMock()
    method_frame = MagicMock()
    method_frame.consumer_tag = None
    method_frame.delivery_tag = 123
    properties = MagicMock()
    body = b'{"data": "test"}'

    with pytest.raises(InvalidMessageError):
        consumer._route_event_handler(channel, method_frame, properties, body)


def test_sync_consumer_route_event_handler_missing_delivery_tag_expect_error(
    config: RabbitMQConnectionConfig,
) -> None:
    """delivery_tag가 None일 때 InvalidMessageError가 발생함을 검증한다."""
    consumer = RabbitMQEventConsumer(config)
    consumer.register(SampleIntegrationEvent, MagicMock())

    channel = MagicMock()
    method_frame = MagicMock()
    method_frame.consumer_tag = "test_tag"
    method_frame.delivery_tag = None
    properties = MagicMock()
    body = b'{"data": "test"}'

    with pytest.raises(InvalidMessageError):
        consumer._route_event_handler(channel, method_frame, properties, body)


@pytest.mark.asyncio
async def test_async_consumer_route_event_handler_missing_consumer_tag_expect_error(
    config: RabbitMQConnectionConfig,
) -> None:
    """비동기 consumer에서 consumer_tag가 None일 때 InvalidMessageError가 발생함을 검증한다."""
    consumer = AsyncRabbitMQEventConsumer(config)
    consumer.register(SampleIntegrationEvent, AsyncMock())

    message = AsyncMock()
    message.consumer_tag = None
    message.delivery_tag = 123
    message.body = b'{"data": "test"}'

    with pytest.raises(InvalidMessageError):
        await consumer._route_event_handler(message)


@pytest.mark.asyncio
async def test_async_consumer_route_event_handler_missing_delivery_tag_expect_error(
    config: RabbitMQConnectionConfig,
) -> None:
    """비동기 consumer에서 delivery_tag가 None일 때 InvalidMessageError가 발생함을 검증한다."""
    consumer = AsyncRabbitMQEventConsumer(config)
    consumer.register(SampleIntegrationEvent, AsyncMock())

    message = AsyncMock()
    message.consumer_tag = "test_tag"
    message.delivery_tag = None
    message.body = b'{"data": "test"}'

    with pytest.raises(InvalidMessageError):
        await consumer._route_event_handler(message)


@pytest.mark.asyncio
async def test_async_consumer_route_event_handler_success_expect_ack(
    config: RabbitMQConnectionConfig,
) -> None:
    """비동기 consumer가 메시지를 성공적으로 처리하면 ack를 호출함을 검증한다."""
    consumer = AsyncRabbitMQEventConsumer(config)
    handler = AsyncMock()
    consumer.register(SampleIntegrationEvent, handler)

    # Set up the type_lookup to map consumer_tag to event type
    consumer.type_lookup["test_tag"] = SampleIntegrationEvent

    message = AsyncMock()
    message.consumer_tag = "test_tag"
    message.delivery_tag = 123
    message.body = b'{"data": "test"}'

    await consumer._route_event_handler(message)

    handler.assert_awaited_once()
    message.ack.assert_awaited_once()


def test_sync_consumer_route_event_handler_success_expect_ack(
    config: RabbitMQConnectionConfig,
) -> None:
    """동기 consumer가 메시지를 성공적으로 처리하면 ack를 호출함을 검증한다."""
    consumer = RabbitMQEventConsumer(config)
    handler = MagicMock()
    consumer.register(SampleIntegrationEvent, handler)

    # Set up the type_lookup to map consumer_tag to event type
    consumer.type_lookup["test_tag"] = SampleIntegrationEvent

    channel = MagicMock()
    method_frame = MagicMock()
    method_frame.consumer_tag = "test_tag"
    method_frame.delivery_tag = 123
    properties = MagicMock()
    body = b'{"data": "test"}'

    consumer._route_event_handler(channel, method_frame, properties, body)

    handler.assert_called_once()
    channel.basic_ack.assert_called_once_with(123)


def test_sync_consumer_register_multiple_handlers_expect_all_called(
    config: RabbitMQConnectionConfig,
) -> None:
    """동일 이벤트에 복수 핸들러 등록 시 모두 호출됨을 검증한다."""
    consumer = RabbitMQEventConsumer(config)
    handler1 = MagicMock()
    handler2 = MagicMock()
    consumer.register(SampleIntegrationEvent, handler1)
    consumer.register(SampleIntegrationEvent, handler2)

    assert len(consumer.handlers[SampleIntegrationEvent]) == 2

    # Set up the type_lookup to map consumer_tag to event type
    consumer.type_lookup["test_tag"] = SampleIntegrationEvent

    channel = MagicMock()
    method_frame = MagicMock()
    method_frame.consumer_tag = "test_tag"
    method_frame.delivery_tag = 123
    properties = MagicMock()
    body = b'{"data": "test"}'

    consumer._route_event_handler(channel, method_frame, properties, body)

    handler1.assert_called_once()
    handler2.assert_called_once()
    channel.basic_ack.assert_called_once_with(123)


@pytest.mark.asyncio
async def test_async_consumer_register_multiple_handlers_expect_all_called(
    config: RabbitMQConnectionConfig,
) -> None:
    """비동기 consumer에서 동일 이벤트에 복수 핸들러 등록 시 모두 호출됨을 검증한다."""
    consumer = AsyncRabbitMQEventConsumer(config)
    handler1 = AsyncMock()
    handler2 = AsyncMock()
    consumer.register(SampleIntegrationEvent, handler1)
    consumer.register(SampleIntegrationEvent, handler2)

    assert len(consumer.handlers[SampleIntegrationEvent]) == 2

    # Set up the type_lookup to map consumer_tag to event type
    consumer.type_lookup["test_tag"] = SampleIntegrationEvent

    message = AsyncMock()
    message.consumer_tag = "test_tag"
    message.delivery_tag = 123
    message.body = b'{"data": "test"}'

    await consumer._route_event_handler(message)

    handler1.assert_awaited_once()
    handler2.assert_awaited_once()
    message.ack.assert_awaited_once()


def test_sync_consumer_check_if_event_set_when_set_expect_stop_consuming(
    config: RabbitMQConnectionConfig,
) -> None:
    """stop_event가 설정되면 channel.stop_consuming이 호출됨을 검증한다."""
    import threading

    consumer = RabbitMQEventConsumer(config)
    stop_event = threading.Event()
    consumer.set_stop_event(stop_event)
    consumer.channel = MagicMock()
    consumer.connection = MagicMock()
    stop_event.set()

    consumer._check_if_event_set()

    consumer.channel.stop_consuming.assert_called_once()


def test_sync_consumer_check_if_event_set_when_not_set_expect_callback_added(
    config: RabbitMQConnectionConfig,
) -> None:
    """stop_event가 설정되지 않았을 때 callback이 다시 등록됨을 검증한다."""
    import threading

    consumer = RabbitMQEventConsumer(config)
    stop_event = threading.Event()
    consumer.set_stop_event(stop_event)
    consumer.channel = MagicMock()
    consumer.connection = MagicMock()

    consumer._check_if_event_set()

    consumer.connection.add_callback_threadsafe.assert_called_once()


def test_sync_consumer_initialize_expect_connection_and_channel_created(
    config: RabbitMQConnectionConfig,
) -> None:
    """initialize가 connection과 channel을 생성하고 queue를 선언함을 검증한다."""
    from unittest.mock import patch

    consumer = RabbitMQEventConsumer(config)
    consumer.register(SampleIntegrationEvent, MagicMock())

    mock_channel = MagicMock()
    mock_channel.basic_consume.return_value = "consumer_tag_1"
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch(
        "spakky.plugins.rabbitmq.event.consumer.BlockingConnection",
        return_value=mock_connection,
    ):
        consumer.initialize()

    mock_channel.queue_declare.assert_called_once_with("SampleIntegrationEvent")
    mock_channel.basic_consume.assert_called_once()
    assert consumer.type_lookup["consumer_tag_1"] == SampleIntegrationEvent


def test_sync_consumer_dispose_expect_channel_and_connection_closed(
    config: RabbitMQConnectionConfig,
) -> None:
    """dispose가 channel과 connection을 닫음을 검증한다."""
    consumer = RabbitMQEventConsumer(config)
    consumer.channel = MagicMock()
    consumer.connection = MagicMock()

    consumer.dispose()

    consumer.channel.close.assert_called_once()
    consumer.connection.close.assert_called_once()


def test_sync_consumer_run_expect_start_consuming_called(
    config: RabbitMQConnectionConfig,
) -> None:
    """run이 start_consuming을 호출함을 검증한다."""
    consumer = RabbitMQEventConsumer(config)
    consumer.channel = MagicMock()
    consumer.connection = MagicMock()

    consumer.run()

    consumer.connection.add_callback_threadsafe.assert_called_once()
    consumer.channel.start_consuming.assert_called_once()


@pytest.mark.asyncio
async def test_async_consumer_initialize_async_expect_connection_and_channel_created(
    config: RabbitMQConnectionConfig,
) -> None:
    """initialize_async가 connection과 channel을 생성함을 검증한다."""
    from unittest.mock import patch

    consumer = AsyncRabbitMQEventConsumer(config)
    consumer.register(SampleIntegrationEvent, AsyncMock())

    mock_queue = AsyncMock()
    mock_queue.consume.return_value = "consumer_tag_1"
    mock_channel = AsyncMock()
    mock_channel.declare_queue.return_value = mock_queue
    mock_connection = AsyncMock()
    mock_connection.channel.return_value = mock_channel

    with patch(
        "spakky.plugins.rabbitmq.event.consumer.connect_robust",
        new_callable=AsyncMock,
        return_value=mock_connection,
    ):
        await consumer.initialize_async()

    mock_channel.declare_queue.assert_called_once_with("SampleIntegrationEvent")
    mock_queue.consume.assert_called_once()
    assert consumer.type_lookup["consumer_tag_1"] == SampleIntegrationEvent


@pytest.mark.asyncio
async def test_async_consumer_dispose_async_expect_channel_and_connection_closed(
    config: RabbitMQConnectionConfig,
) -> None:
    """dispose_async가 channel과 connection을 닫음을 검증한다."""
    consumer = AsyncRabbitMQEventConsumer(config)
    consumer.channel = AsyncMock()
    consumer.connection = AsyncMock()

    await consumer.dispose_async()

    consumer.channel.close.assert_awaited_once()
    consumer.connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_consumer_run_async_expect_wait_for_stop_event(
    config: RabbitMQConnectionConfig,
) -> None:
    """run_async가 stop_event를 대기함을 검증한다."""
    import asyncio

    consumer = AsyncRabbitMQEventConsumer(config)
    stop_event = asyncio.Event()
    consumer.set_stop_event(stop_event)

    async def set_stop_after_delay() -> None:
        await asyncio.sleep(0.01)
        stop_event.set()

    asyncio.create_task(set_stop_after_delay())
    await consumer.run_async()

    assert stop_event.is_set()
