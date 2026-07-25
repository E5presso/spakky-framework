"""Unit tests for RabbitMQ event transports."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pika import BasicProperties

from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig
from spakky.plugins.rabbitmq.event.transport import (
    AsyncRabbitMQEventTransport,
    RabbitMQEventTransport,
)


def test_sync_transport_send_without_exchange_name_expect_default_exchange() -> None:
    """exchange_name이 None일 때 기본 exchange로 발행함을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = None

    transport = RabbitMQEventTransport(config)

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch(
        "spakky.plugins.rabbitmq.event.transport.BlockingConnection",
        return_value=mock_connection,
    ):
        transport.send("test_event", b'{"key": "value"}', {})

    mock_channel.queue_declare.assert_called_once_with("test_event", durable=True)
    mock_channel.exchange_declare.assert_not_called()
    mock_channel.queue_bind.assert_not_called()
    mock_channel.basic_publish.assert_called_once_with(
        "",
        "test_event",
        b'{"key": "value"}',
        properties=BasicProperties(headers={}),
    )


@pytest.mark.asyncio
async def test_async_transport_send_without_exchange_name_expect_default_exchange() -> (
    None
):
    """exchange_name이 None일 때 기본 exchange로 발행함을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = None

    transport = AsyncRabbitMQEventTransport(config)

    mock_default_exchange = AsyncMock()
    mock_channel = AsyncMock()
    mock_channel.default_exchange = mock_default_exchange
    mock_channel.declare_queue = AsyncMock()
    mock_channel.close = AsyncMock()

    mock_connection = AsyncMock()
    mock_connection.channel = AsyncMock(return_value=mock_channel)

    mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "spakky.plugins.rabbitmq.event.transport.connect_robust",
        new_callable=AsyncMock,
        return_value=mock_connection,
    ):
        await transport.send("test_event", b'{"key": "value"}', {})

    mock_channel.declare_exchange.assert_not_called()
    mock_channel.declare_queue.assert_called_once_with("test_event", durable=True)
    mock_default_exchange.publish.assert_called_once()


def test_sync_transport_send_with_exchange_name_expect_exchange_declared() -> None:
    """exchange_name이 있을 때 exchange가 선언되고 queue가 바인딩됨을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = "test_exchange"

    transport = RabbitMQEventTransport(config)

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch(
        "spakky.plugins.rabbitmq.event.transport.BlockingConnection",
        return_value=mock_connection,
    ):
        transport.send("test_event", b'{"key": "value"}', {})

    mock_channel.queue_declare.assert_called_once_with("test_event", durable=True)
    mock_channel.exchange_declare.assert_called_once_with("test_exchange")
    mock_channel.queue_bind.assert_called_once_with(
        "test_event", "test_exchange", "test_event"
    )
    mock_channel.basic_publish.assert_called_once_with(
        "test_exchange",
        "test_event",
        b'{"key": "value"}',
        properties=BasicProperties(headers={}),
    )


@pytest.mark.asyncio
async def test_async_transport_send_with_exchange_name_expect_exchange_declared() -> (
    None
):
    """비동기 transport에서 exchange_name이 있을 때 exchange가 선언됨을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = "test_exchange"

    transport = AsyncRabbitMQEventTransport(config)

    mock_exchange = AsyncMock()
    mock_queue = AsyncMock()
    mock_channel = AsyncMock()
    mock_channel.declare_exchange.return_value = mock_exchange
    mock_channel.declare_queue.return_value = mock_queue
    mock_channel.close = AsyncMock()

    mock_connection = AsyncMock()
    mock_connection.channel = AsyncMock(return_value=mock_channel)

    mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "spakky.plugins.rabbitmq.event.transport.connect_robust",
        new_callable=AsyncMock,
        return_value=mock_connection,
    ):
        await transport.send("test_event", b'{"key": "value"}', {})

    mock_channel.declare_exchange.assert_called_once_with("test_exchange")
    mock_channel.declare_queue.assert_called_once_with("test_event", durable=True)
    mock_queue.bind.assert_called_once_with(mock_exchange, "test_event")
    mock_exchange.publish.assert_called_once()


def test_sync_transport_send_with_partition_key_expect_routing_unchanged() -> None:
    """partition_key를 받아도 RabbitMQ 발행 인자가 달라지지 않음을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = None

    transport = RabbitMQEventTransport(config)

    mock_channel = MagicMock()
    mock_connection = MagicMock()
    mock_connection.channel.return_value = mock_channel

    with patch(
        "spakky.plugins.rabbitmq.event.transport.BlockingConnection",
        return_value=mock_connection,
    ):
        transport.send("test_event", b'{"key": "value"}', {}, "ORD-1")

    mock_channel.basic_publish.assert_called_once_with(
        "",
        "test_event",
        b'{"key": "value"}',
        properties=BasicProperties(headers={}),
    )


@pytest.mark.asyncio
async def test_async_transport_send_with_partition_key_expect_routing_unchanged() -> (
    None
):
    """비동기 경로에서 partition_key가 라우팅 키를 바꾸지 않음을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = None

    transport = AsyncRabbitMQEventTransport(config)

    mock_default_exchange = AsyncMock()
    mock_channel = AsyncMock()
    mock_channel.default_exchange = mock_default_exchange
    mock_channel.declare_queue = AsyncMock()
    mock_channel.close = AsyncMock()

    mock_connection = AsyncMock()
    mock_connection.channel = AsyncMock(return_value=mock_channel)
    mock_connection.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_connection.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "spakky.plugins.rabbitmq.event.transport.connect_robust",
        new_callable=AsyncMock,
        return_value=mock_connection,
    ):
        await transport.send("test_event", b'{"key": "value"}', {}, "ORD-1")

    assert mock_default_exchange.publish.call_args.kwargs == {
        "routing_key": "test_event"
    }


def test_sync_transport_flush_expect_no_broker_round_trip() -> None:
    """send가 이미 발행을 마치므로 flush가 브로커에 다시 접속하지 않음을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = None

    transport = RabbitMQEventTransport(config)

    with patch(
        "spakky.plugins.rabbitmq.event.transport.BlockingConnection"
    ) as mock_connection_cls:
        assert transport.flush() is None

    mock_connection_cls.assert_not_called()


@pytest.mark.asyncio
async def test_async_transport_flush_expect_no_broker_round_trip() -> None:
    """send가 이미 발행을 마치므로 flush가 브로커에 다시 접속하지 않음을 검증한다."""
    config = MagicMock(spec=RabbitMQConnectionConfig)
    config.connection_string = "amqp://test:test@localhost:5672/"
    config.exchange_name = None

    transport = AsyncRabbitMQEventTransport(config)

    with patch(
        "spakky.plugins.rabbitmq.event.transport.connect_robust",
        new_callable=AsyncMock,
    ) as mock_connect:
        assert await transport.flush() is None

    mock_connect.assert_not_awaited()
