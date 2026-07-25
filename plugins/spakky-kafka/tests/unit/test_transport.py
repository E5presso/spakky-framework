"""Unit tests for Kafka event transports.

Tests send, topic creation, and delivery reporting
for both synchronous and asynchronous Kafka event transports.
"""

from asyncio import (
    Future,
    create_task,
    get_running_loop,
    locks,
    new_event_loop,
    run_coroutine_threadsafe,
)
from threading import Event, Thread
from typing import Any
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.structs import RecordMetadata, TopicPartition
from confluent_kafka import KafkaError
from spakky.event.error import (
    EventDeliveryRejectedError,
    EventTransportNotRunningError,
)

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.transport import (
    AsyncKafkaEventTransport,
    KafkaEventTransport,
    _pending_deliveries,
)


def _delivered_record() -> Future[RecordMetadata]:
    """Return the delivery an aiokafka producer resolves once the broker acked."""
    delivery: Future[RecordMetadata] = get_running_loop().create_future()
    delivery.set_result(
        RecordMetadata(
            topic="TestEvent",
            partition=0,
            topic_partition=TopicPartition("TestEvent", 0),
            offset=0,
            timestamp=0,
            timestamp_type=0,
            log_start_offset=0,
        )
    )
    return delivery


async def _delivered_record_async() -> Future[RecordMetadata]:
    """Return a resolved delivery created on the currently running loop."""
    return _delivered_record()


def _rejected_record(rejection: Exception) -> Future[RecordMetadata]:
    """Return the delivery an aiokafka producer resolves when the broker rejects."""
    delivery: Future[RecordMetadata] = get_running_loop().create_future()
    delivery.set_exception(rejection)
    return delivery


def _claimed_deliveries() -> list[Future[RecordMetadata]]:
    """Return the records this execution context still owes a flush."""
    return _pending_deliveries.get() or []


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
    """동기 KafkaEventTransport가 멱등 발행 설정으로 producer를 만드는지 검증한다."""
    transport = KafkaEventTransport(config)

    assert transport.config is config
    mock_admin_cls.assert_called_once_with(config.connection_configuration_dict)
    producer_config = mock_producer_cls.call_args[0][0]
    assert producer_config["enable.idempotence"] is True
    assert producer_config["acks"] == "all"


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
def test_sync_transport_send_expect_produce_without_flush(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport의 send가 produce와 poll만 호출하고 flush는 미루는지 검증한다."""
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
        key=None,
        headers={},
        callback=transport._message_delivery_report,
    )
    mock_producer.poll.assert_called_once_with(0)
    mock_producer.flush.assert_not_called()


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_batch_expect_single_flush_for_two_sends(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport가 2건 발행 후 flush 1회로 배치를 확정하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin

    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    transport = KafkaEventTransport(config)
    transport.send("TestEvent", b"{}", {})
    transport.send("TestEvent", b"{}", {})
    transport.flush()

    assert mock_producer.produce.call_count == 2
    mock_producer.flush.assert_called_once()


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_stop_expect_queued_records_flushed(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """애플리케이션 종료 시 큐에 남은 레코드를 flush로 내보내는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin

    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    transport = KafkaEventTransport(config)
    transport.set_stop_event(Event())
    transport.start()
    transport.send("TestEvent", b"{}", {})
    transport.stop()

    mock_producer.flush.assert_called_once()


@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_async_transport_init_expect_success(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 AsyncKafkaEventTransport가 올바르게 초기화되는지 검증한다."""
    transport = AsyncKafkaEventTransport(config)

    assert transport.config is config
    mock_admin_cls.assert_called_once_with(config.connection_configuration_dict)


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_expect_record_handed_to_started_producer(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 transport의 send가 시작된 producer에 레코드를 넘기는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_producer = AsyncMock()
    mock_producer.send.return_value = _delivered_record()
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.send(
        "TestEvent", b'{"key": "value"}', {"traceparent": "00-abc-def-01"}
    )

    mock_aio_producer_cls.assert_called_once_with(
        bootstrap_servers=config.bootstrap_servers,
        client_id=config.client_id,
        enable_idempotence=True,
        acks="all",
    )
    mock_producer.start.assert_awaited_once()
    mock_producer.send.assert_awaited_once_with(
        topic="TestEvent",
        value=b'{"key": "value"}',
        key=None,
        headers=[("traceparent", b"00-abc-def-01")],
    )
    mock_producer.stop.assert_not_awaited()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_expect_no_broker_wait_before_flush(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """send가 broker ack를 기다리지 않아 두 레코드가 한 배치로 묶이는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin

    mock_producer = AsyncMock()
    mock_producer.send.side_effect = [_delivered_record(), _delivered_record()]
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.send("TestEvent", b"{}", {})
    await transport.send("TestEvent", b"{}", {})

    assert mock_producer.send.await_count == 2
    mock_producer.flush.assert_not_awaited()

    await transport.flush()

    mock_aio_producer_cls.assert_called_once()
    mock_producer.flush.assert_awaited_once()
    assert _claimed_deliveries() == []


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_flush_rejected_record_expect_broker_error_raised(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """broker가 거부한 레코드를 flush가 EventDeliveryRejectedError로 올리는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin

    mock_producer = AsyncMock()
    mock_producer.send.side_effect = [
        _rejected_record(ConnectionError("Broker rejected the record")),
        _delivered_record(),
    ]
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.send("TestEvent", b"{}", {})
    await transport.send("TestEvent", b"{}", {})

    with pytest.raises(EventDeliveryRejectedError) as rejection:
        await transport.flush()

    assert rejection.value.reasons == ["Broker rejected the record"]


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_concurrent_publishers_expect_rejection_to_its_own_sender(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동시 발행에서 거부된 레코드의 실패가 그 레코드를 보낸 발행자에게만 전달된다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin

    mock_producer = AsyncMock()
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()

    rejected_publisher_started = locks.Event()
    healthy_publisher_flushed = locks.Event()

    async def publish_rejected_record() -> None:
        """발행자 A: 거부될 레코드를 보내고, 동시 발행자가 flush를 마친 뒤 flush한다."""
        mock_producer.send.return_value = _rejected_record(
            ConnectionError("Broker rejected the record")
        )
        await transport.send("TestEvent", b'{"sender": "rejected"}', {})
        rejected_publisher_started.set()
        await healthy_publisher_flushed.wait()
        await transport.flush()

    async def publish_healthy_record() -> None:
        """발행자 B: 정상 레코드를 보내고 먼저 flush한다."""
        await rejected_publisher_started.wait()
        mock_producer.send.return_value = _delivered_record()
        await transport.send("TestEvent", b'{"sender": "healthy"}', {})
        await transport.flush()
        healthy_publisher_flushed.set()

    healthy_publisher = create_task(publish_healthy_record())
    with pytest.raises(EventDeliveryRejectedError):
        await publish_rejected_record()
    await healthy_publisher


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_stop_async_expect_buffered_record_delivered_then_closed(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """애플리케이션 종료 시 남은 레코드를 내보낸 뒤 producer를 닫는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin
    mock_producer = AsyncMock()
    mock_producer.send.return_value = _delivered_record()
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.send("TestEvent", b"{}", {})
    await transport.stop_async()

    mock_producer.flush.assert_awaited_once()
    mock_producer.stop.assert_awaited_once()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_stop_async_with_rejected_record_expect_producer_closed(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """종료 시 마지막 레코드가 거부되어도 producer를 닫고 예외를 밖으로 내지 않는다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin
    mock_producer = AsyncMock()
    mock_producer.send.return_value = _rejected_record(
        ConnectionError("Broker rejected the record")
    )
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.send("TestEvent", b"{}", {})
    await transport.stop_async()

    mock_producer.stop.assert_awaited_once()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_before_start_expect_not_running_error(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """애플리케이션이 transport를 시작하기 전 발행은 not-running 에러로 거부된다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin

    transport = AsyncKafkaEventTransport(config)

    with pytest.raises(EventTransportNotRunningError):
        await transport.send("TestEvent", b"{}", {})


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_after_stop_expect_not_running_error(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """종료 후 도착한 발행은 전달 실패가 아니라 not-running 에러로 구분된다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin
    mock_producer = AsyncMock()
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.stop_async()

    with pytest.raises(EventTransportNotRunningError):
        await transport.send("TestEvent", b"{}", {})
    with pytest.raises(EventTransportNotRunningError):
        await transport.flush()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_from_other_loop_expect_routed_to_producer_loop(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """producer를 만든 루프가 아닌 곳에서 발행해도 producer 루프로 라우팅됨을 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin
    mock_producer = AsyncMock()
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    producer_loop = new_event_loop()
    producer_loop_thread = Thread(target=producer_loop.run_forever, daemon=True)
    producer_loop_thread.start()
    try:
        run_coroutine_threadsafe(transport.start_async(), producer_loop).result()
        mock_producer.send.return_value = run_coroutine_threadsafe(
            _delivered_record_async(), producer_loop
        ).result()

        await transport.send("TestEvent", b"{}", {})
        await transport.flush()

        assert transport._running_producer.loop is producer_loop
        mock_producer.send.assert_awaited_once()
        mock_producer.flush.assert_awaited_once()
    finally:
        producer_loop.call_soon_threadsafe(producer_loop.stop)
        producer_loop_thread.join()
        producer_loop.close()


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_start_async_with_sasl_config_expect_security_kwargs(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """비동기 producer 생성 시 SASL/security 설정을 aiokafka kwargs로 전달한다."""
    from spakky.plugins.kafka.common.constants import SPAKKY_KAFKA_CONFIG_ENV_PREFIX

    monkeypatch.setenv(f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}GROUP_ID", "test-group")
    monkeypatch.setenv(f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}CLIENT_ID", "secure-client")
    monkeypatch.setenv(
        f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}BOOTSTRAP_SERVERS", "secure:9093"
    )
    monkeypatch.setenv(f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv(f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_MECHANISM", "PLAIN")
    monkeypatch.setenv(f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_USERNAME", "api-key")
    monkeypatch.setenv(f"{SPAKKY_KAFKA_CONFIG_ENV_PREFIX}SASL_PASSWORD", "api-secret")

    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin
    mock_producer = AsyncMock()
    mock_aio_producer_cls.return_value = mock_producer

    config = KafkaConnectionConfig()
    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()

    mock_aio_producer_cls.assert_called_once_with(
        bootstrap_servers="secure:9093",
        client_id="secure-client",
        enable_idempotence=True,
        acks="all",
        security_protocol="SASL_SSL",
        sasl_mechanism="PLAIN",
        sasl_plain_username="api-key",
        sasl_plain_password="api-secret",
    )


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_send_with_partition_key_expect_encoded_key(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """동기 transport가 partition_key를 bytes key로 인코딩해 produce하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    transport = KafkaEventTransport(config)
    transport.send("TestEvent", b"{}", {}, "ORD-42")

    mock_producer.produce.assert_called_once_with(
        topic="TestEvent",
        value=b"{}",
        key=b"ORD-42",
        headers={},
        callback=transport._message_delivery_report,
    )


@pytest.mark.asyncio
@patch("spakky.plugins.kafka.event.transport.AIOKafkaProducer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
async def test_async_transport_send_with_partition_key_expect_encoded_key(
    mock_admin_cls: MagicMock,
    mock_aio_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """비동기 transport가 partition_key를 bytes key로 인코딩해 전송하는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = set()
    mock_admin_cls.return_value = mock_admin

    mock_producer = AsyncMock()
    mock_producer.send.return_value = _delivered_record()
    mock_aio_producer_cls.return_value = mock_producer

    transport = AsyncKafkaEventTransport(config)
    await transport.start_async()
    await transport.send("TestEvent", b"{}", {}, "ORD-43")

    mock_producer.send.assert_awaited_once_with(
        topic="TestEvent",
        value=b"{}",
        key=b"ORD-43",
        headers=[],
    )


@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_async_transport_set_stop_event_expect_no_producer_interaction(
    mock_admin_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """transport는 폴링 루프가 없으므로 stop event를 받아도 아무 것도 하지 않는다."""
    mock_admin_cls.return_value = MagicMock()

    transport = AsyncKafkaEventTransport(config)

    assert transport.set_stop_event(locks.Event()) is None


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_flush_rejected_record_expect_broker_error_raised(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """delivery callback이 받은 거부를 flush가 예외로 올리는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin
    mock_producer_cls.return_value = MagicMock()

    transport = KafkaEventTransport(config)
    transport.send("TestEvent", b"{}", {})
    transport._message_delivery_report(MagicMock(spec=KafkaError), MagicMock())

    with pytest.raises(EventDeliveryRejectedError):
        transport.flush()


@patch("spakky.plugins.kafka.event.transport.Producer")
@patch("spakky.plugins.kafka.event.transport.AdminClient")
def test_sync_transport_flush_after_rejection_expect_next_batch_unaffected(
    mock_admin_cls: MagicMock,
    mock_producer_cls: MagicMock,
    config: KafkaConnectionConfig,
) -> None:
    """거부를 한 번 올린 뒤 다음 배치의 flush가 다시 실패하지 않는지 검증한다."""
    mock_admin = MagicMock()
    mock_admin.list_topics.return_value.topics.keys.return_value = {"TestEvent"}
    mock_admin_cls.return_value = mock_admin
    mock_producer_cls.return_value = MagicMock()

    transport = KafkaEventTransport(config)
    transport._message_delivery_report(MagicMock(spec=KafkaError), MagicMock())
    with pytest.raises(EventDeliveryRejectedError):
        transport.flush()

    transport.send("TestEvent", b"{}", {})
    transport.flush()
