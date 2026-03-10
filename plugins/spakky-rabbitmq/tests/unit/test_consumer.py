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
