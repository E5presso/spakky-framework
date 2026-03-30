"""Unit tests for Kafka event transports.

Tests send, topic creation, and delivery reporting
for both synchronous and asynchronous Kafka event transports.
"""

from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.transport import (
    AsyncKafkaEventTransport,
    KafkaEventTransport,
)


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


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_init_expect_success(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 KafkaEventTransport가 올바르게 초기화되는지 검증한다."""
    transport = KafkaEventTransport(config)

    assert transport.config is config
    mock_admin_cls.assert_called_once_with(config.configuration_dict)
    mock_producer_cls.assert_called_once()


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_create_topic_new_topic_expect_created(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport의 _create_topic이 새 토픽을 생성하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"existing_topic"}
    mock_admin_cls.return_value = mock_admin

    transport = KafkaEventTransport(config)
    transport._create_topic("new_topic")

    mock_admin.create_topics.assert_called_once()


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_create_topic_existing_topic_expect_skipped(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport의 _create_topic이 기존 토픽 생성을 건너뛰는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"existing_topic"}
    mock_admin_cls.return_value = mock_admin

    transport = KafkaEventTransport(config)
    transport._create_topic("existing_topic")

    mock_admin.create_topics.assert_not_called()


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_message_delivery_report_success_expect_log(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport의 delivery report가 성공 시 로그를 출력하는지 검증한다."""
    transport = KafkaEventTransport(config)

    mock_message = MagicMock()
    mock_message.topic.return_value = "test_topic"
    mock_message.partition.return_value = 0
    mock_message.offset.return_value = 42

    # Should not raise
    transport._message_delivery_report(None, mock_message)


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_send_expect_produce_and_flush(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport의 send가 produce, poll, flush를 호출하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    transport = KafkaEventTransport(config)
    transport.send("TestEvent", b'{"key": "value"}', {})

    mock_producer.produce.assert_called_once_with(
        topic="TestEvent",
        value=b'{"key": "value"}',
        headers={},
        callback=transport._message_delivery_report,
    )
    mock_producer.poll.assert_called_once_with(0)
    mock_producer.flush.assert_called_once()


@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_async_transport_init_expect_success(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 AsyncKafkaEventTransport가 올바르게 초기화되는지 검증한다."""
    transport = AsyncKafkaEventTransport(config)

    assert transport.config is config
    mock_admin_cls.assert_called_once_with(config.configuration_dict)


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_expect_produce_and_flush(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 transport의 send가 produce, poll, flush를 호출하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.send("TestEvent", b'{"key": "value"}', {})

    mock_producer.produce.assert_called_once_with(
        topic="TestEvent",
        value=b'{"key": "value"}',
        headers={},
        callback=transport._message_delivery_report,
    )
    mock_producer.poll.assert_called_once_with(0)
    mock_producer.flush.assert_called_once()
