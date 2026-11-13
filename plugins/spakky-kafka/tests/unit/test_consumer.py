"""Unit tests for the Kafka event consumer Pods.

The Pods own registration, topic creation, the per-subscriber workers' lifecycle
and redrive routing; what a worker does with a message is covered in
`test_worker.py`.
"""

import asyncio
import threading
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from confluent_kafka import KafkaError, KafkaException
from spakky.event.delivery import RetryMode, RetryPolicy
from spakky.event.error import SubscriptionNotFoundError
from spakky.event.redrive import RedriveResult
from spakky.event.subscription import (
    DuplicateEventHandlerNameError,
    InvalidSubscriberNameError,
)
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.kafka.common.config import KafkaConnectionConfig
from spakky.plugins.kafka.event.consumer import (
    AsyncKafkaEventConsumer,
    KafkaEventConsumer,
)
from tests.unit.harness import WORKER_MODULE, AnotherEvent, RenamedEvent, SampleEvent

CONSUMER_MODULE = "spakky.plugins.kafka.event.consumer"


@pytest.fixture(name="admin", autouse=True)
def admin_fixture() -> Any:
    """Replace the admin client so no test reaches a broker."""
    with patch(f"{CONSUMER_MODULE}.AdminClient") as admin_cls:
        admin = admin_cls.return_value
        admin.list_topics.return_value.topics = {}
        admin.create_topics.return_value = {}
        yield admin


def created_topics(admin: MagicMock) -> set[str]:
    """Names of the topics the consumer asked the broker to create."""
    return {topic.topic for topic in admin.create_topics.call_args.args[0]}


def test_sync_consumer_without_handlers_expect_no_clients_opened(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """발행 전용 또는 async 전용 앱의 빈 동기 소비자는 브로커 클라이언트를 열지 않는다."""
    with patch(f"{WORKER_MODULE}.Consumer") as consumer_cls:
        consumer = KafkaEventConsumer(config)
        consumer.set_stop_event(threading.Event())

        consumer.initialize()
        consumer.run()
        consumer.dispose()

    consumer_cls.assert_not_called()
    admin.list_topics.assert_not_called()


def test_sync_consumer_register_expect_one_worker_per_subscriber(
    config: KafkaConnectionConfig,
) -> None:
    """핸들러는 구독자별 worker에 모이고, 한 구독자의 여러 이벤트는 한 worker가 맡는다."""
    consumer = KafkaEventConsumer(config)

    consumer.register(SampleEvent, MagicMock())
    consumer.register(SampleEvent, MagicMock(), subscriber="billing")
    consumer.register(AnotherEvent, MagicMock(), subscriber="billing")
    consumer.register(RenamedEvent, MagicMock(), subscriber="shipping")

    assert set(consumer.workers) == {None, "billing", "shipping"}
    assert consumer.workers[None].group_id == "test-group"
    assert consumer.workers["billing"].group_id == "test-group.billing"
    assert consumer.workers["billing"].subscribed_topics == [
        "SampleEvent",
        "AnotherEvent",
    ]
    assert consumer.workers["shipping"].subscribed_topics == ["external.renamed.v1"]


def test_sync_consumer_register_same_event_twice_expect_both_handlers_in_subscription(
    config: KafkaConnectionConfig,
) -> None:
    """같은 구독자·이벤트에 등록한 핸들러는 한 구독에 이름과 함께 쌓인다."""
    consumer = KafkaEventConsumer(config)

    consumer.register(SampleEvent, MagicMock(), handler_name="first")
    consumer.register(SampleEvent, MagicMock())

    handlers = consumer.subscriptions.get(None, SampleEvent).handlers
    assert [handler.name for handler in handlers] == ["first", "SampleEvent#1"]


def test_sync_consumer_register_invalid_names_expect_rejected(
    config: KafkaConnectionConfig,
) -> None:
    """토픽 이름이 될 수 없는 구독자 이름과 중복 핸들러 이름은 등록에서 거절된다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock(), handler_name="first")

    with pytest.raises(InvalidSubscriberNameError):
        consumer.register(SampleEvent, MagicMock(), subscriber="bill.ing")
    with pytest.raises(DuplicateEventHandlerNameError):
        consumer.register(SampleEvent, MagicMock(), handler_name="first")


def test_sync_consumer_set_propagator_expect_existing_and_later_workers_traced(
    config: KafkaConnectionConfig,
) -> None:
    """propagator는 이미 만든 worker와 나중에 만드는 worker 모두에 전달된다."""
    consumer = KafkaEventConsumer(config)
    propagator = W3CTracePropagator()
    consumer.register(SampleEvent, MagicMock())

    consumer.set_propagator(propagator)
    consumer.register(SampleEvent, MagicMock(), subscriber="billing")

    assert consumer.workers[None].propagator is propagator
    assert consumer.workers["billing"].propagator is propagator


def test_sync_consumer_register_auth_boundary_expect_shared_with_every_worker(
    config: KafkaConnectionConfig,
) -> None:
    """auth 경계로 표시한 엔드포인트는 모든 구독자의 worker가 함께 본다."""
    consumer = KafkaEventConsumer(config)
    endpoint = MagicMock()
    consumer.register(SampleEvent, endpoint)

    consumer.register_auth_boundary(endpoint)
    consumer.register(SampleEvent, MagicMock(), subscriber="billing")

    assert endpoint in consumer.workers[None]._auth_boundary_handlers
    assert endpoint in consumer.workers["billing"]._auth_boundary_handlers


def test_sync_consumer_initialize_expect_per_subscriber_topics_created_and_clients_opened(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """초기화는 이벤트 토픽과 구독자별 DLT를 만들고 구독자마다 자기 group으로 consumer를 연다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())
    consumer.register(SampleEvent, MagicMock(), subscriber="billing")
    future = MagicMock()
    admin.create_topics.return_value = {"SampleEvent": future}

    with (
        patch(f"{WORKER_MODULE}.Consumer") as consumer_cls,
        patch(f"{WORKER_MODULE}.Producer"),
    ):
        consumer.initialize()

    assert created_topics(admin) == {
        "SampleEvent",
        "SampleEvent.dlt",
        "SampleEvent.billing.dlt",
    }
    future.result.assert_called_once_with(config.dead_letter_delivery_timeout)
    assert [call.args[0]["group.id"] for call in consumer_cls.call_args_list] == [
        "test-group",
        "test-group.billing",
    ]


def test_sync_consumer_initialize_delayed_mode_expect_retry_topics_created(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """DELAYED 모드에서는 구독자별 retry 토픽도 함께 만든다."""
    config.retry = RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED)
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())
    consumer.register(SampleEvent, MagicMock(), subscriber="billing")

    with patch(f"{WORKER_MODULE}.Consumer"), patch(f"{WORKER_MODULE}.Producer"):
        consumer.initialize()

    assert created_topics(admin) == {
        "SampleEvent",
        "SampleEvent.dlt",
        "SampleEvent.retry",
        "SampleEvent.billing.dlt",
        "SampleEvent.billing.retry",
    }


def test_sync_consumer_initialize_all_topics_exist_expect_nothing_created(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """필요한 토픽이 모두 있으면 토픽 생성을 요청하지 않는다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())
    admin.list_topics.return_value.topics = {"SampleEvent": 1, "SampleEvent.dlt": 1}

    with patch(f"{WORKER_MODULE}.Consumer"), patch(f"{WORKER_MODULE}.Producer"):
        consumer.initialize()

    admin.create_topics.assert_not_called()


def test_sync_consumer_initialize_topic_created_concurrently_expect_tolerated(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """다른 소비자가 먼저 만든 토픽은 실패로 보지 않는다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())
    future = MagicMock()
    future.result.side_effect = KafkaException(
        KafkaError(KafkaError.TOPIC_ALREADY_EXISTS)
    )
    admin.create_topics.return_value = {"SampleEvent": future}

    with (
        patch(f"{WORKER_MODULE}.Consumer") as consumer_cls,
        patch(f"{WORKER_MODULE}.Producer"),
    ):
        consumer.initialize()

    consumer_cls.return_value.subscribe.assert_called_once()


def test_sync_consumer_initialize_topic_creation_refused_expect_error_raised(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """토픽을 만들 권한이 없으면 구독을 시작하지 않고 시작 단계에서 실패한다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())
    future = MagicMock()
    future.result.side_effect = KafkaException(
        KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED)
    )
    admin.create_topics.return_value = {"SampleEvent": future}

    with (
        patch(f"{WORKER_MODULE}.Consumer") as consumer_cls,
        patch(f"{WORKER_MODULE}.Producer"),
        pytest.raises(KafkaException),
    ):
        consumer.initialize()

    consumer_cls.assert_not_called()


def test_sync_consumer_run_expect_every_subscriber_polled_on_its_own_thread(
    config: KafkaConnectionConfig,
) -> None:
    """run은 구독자마다 스레드를 띄워 각자의 poll 루프를 정지 신호와 함께 돌린다."""
    consumer = KafkaEventConsumer(config)
    stop_event = threading.Event()
    consumer.set_stop_event(stop_event)
    threads: dict[str, str] = {}

    def record(name: str) -> Any:
        def run(received: threading.Event) -> None:
            assert received is stop_event
            threads[name] = threading.current_thread().name

        return run

    consumer.workers = {
        None: MagicMock(group_id="test-group", run=record("unnamed")),
        "billing": MagicMock(group_id="test-group.billing", run=record("billing")),
    }

    consumer.run()

    assert threads == {
        "unnamed": "KafkaEventConsumer[test-group]",
        "billing": "KafkaEventConsumer[test-group.billing]",
    }


def test_sync_consumer_dispose_expect_every_worker_closed(
    config: KafkaConnectionConfig,
) -> None:
    """dispose는 모든 구독자의 클라이언트를 닫는다."""
    consumer = KafkaEventConsumer(config)
    unnamed = MagicMock()
    billing = MagicMock()
    consumer.workers = {None: unnamed, "billing": billing}

    consumer.dispose()

    unnamed.close.assert_called_once()
    billing.close.assert_called_once()


def test_sync_consumer_redrive_expect_routed_to_the_subscriber_worker_only(
    config: KafkaConnectionConfig,
) -> None:
    """redrive는 지정한 구독자의 worker에만 이벤트 토픽과 limit을 넘긴다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(RenamedEvent, MagicMock())
    consumer.register(RenamedEvent, MagicMock(), subscriber="billing")
    billing = MagicMock()
    billing.redrive.return_value = RedriveResult(succeeded=2, failed=1)
    unnamed = MagicMock()
    consumer.workers = {None: unnamed, "billing": billing}

    result = consumer.redrive(RenamedEvent, subscriber="billing", limit=5)

    assert result == RedriveResult(succeeded=2, failed=1)
    billing.redrive.assert_called_once_with("external.renamed.v1", 5)
    unnamed.redrive.assert_not_called()


def test_sync_consumer_redrive_unregistered_subscription_expect_not_found_error(
    config: KafkaConnectionConfig,
) -> None:
    """등록되지 않은 구독자·이벤트 조합의 redrive는 거절된다."""
    consumer = KafkaEventConsumer(config)
    consumer.register(SampleEvent, MagicMock())

    with pytest.raises(SubscriptionNotFoundError):
        consumer.redrive(SampleEvent, subscriber="billing")


async def test_async_consumer_without_handlers_expect_no_clients_opened(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """발행 전용 또는 sync 전용 앱의 빈 비동기 소비자는 브로커 클라이언트를 열지 않는다."""
    with patch(f"{WORKER_MODULE}.AIOConsumer") as consumer_cls:
        consumer = AsyncKafkaEventConsumer(config)
        consumer.set_stop_event(asyncio.Event())

        await consumer.initialize_async()
        await consumer.run_async()
        await consumer.dispose_async()

    consumer_cls.assert_not_called()
    admin.list_topics.assert_not_called()


def test_async_consumer_register_expect_one_worker_per_subscriber(
    config: KafkaConnectionConfig,
) -> None:
    """비동기 핸들러도 구독자별 worker에 모인다."""
    consumer = AsyncKafkaEventConsumer(config)

    consumer.register(SampleEvent, AsyncMock(), handler_name="first")
    consumer.register(SampleEvent, AsyncMock())
    consumer.register(AnotherEvent, AsyncMock(), subscriber="billing")

    assert set(consumer.workers) == {None, "billing"}
    assert consumer.workers["billing"].group_id == "test-group.billing"
    assert [
        handler.name
        for handler in consumer.subscriptions.get(None, SampleEvent).handlers
    ] == ["first", "SampleEvent#1"]


def test_async_consumer_set_propagator_and_auth_boundary_expect_shared_with_workers(
    config: KafkaConnectionConfig,
) -> None:
    """propagator와 auth 경계 표시는 앞뒤로 만든 모든 worker가 함께 본다."""
    consumer = AsyncKafkaEventConsumer(config)
    propagator = W3CTracePropagator()
    endpoint = AsyncMock()
    consumer.register(SampleEvent, endpoint)

    consumer.set_propagator(propagator)
    consumer.register_auth_boundary(endpoint)
    consumer.register(SampleEvent, AsyncMock(), subscriber="billing")

    assert consumer.workers[None].propagator is propagator
    assert consumer.workers["billing"].propagator is propagator
    assert endpoint in consumer.workers[None]._auth_boundary_handlers
    assert endpoint in consumer.workers["billing"]._auth_boundary_handlers


async def test_async_consumer_initialize_expect_per_subscriber_topics_created_and_clients_opened(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """비동기 초기화도 구독자별 retry·DLT 토픽을 만들고 구독자마다 consumer를 연다."""
    config.retry = RetryPolicy(max_attempts=3, mode=RetryMode.DELAYED)
    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())
    consumer.register(SampleEvent, AsyncMock(), subscriber="billing")
    future = MagicMock()
    admin.create_topics.return_value = {"SampleEvent": future}

    with (
        patch(f"{WORKER_MODULE}.AIOConsumer") as consumer_cls,
        patch(f"{WORKER_MODULE}.AIOKafkaProducer") as producer_cls,
    ):
        consumer_cls.return_value = AsyncMock()
        producer_cls.return_value = AsyncMock()
        await consumer.initialize_async()

    assert created_topics(admin) == {
        "SampleEvent",
        "SampleEvent.dlt",
        "SampleEvent.retry",
        "SampleEvent.billing.dlt",
        "SampleEvent.billing.retry",
    }
    future.result.assert_called_once_with(config.dead_letter_delivery_timeout)
    assert [call.args[0]["group.id"] for call in consumer_cls.call_args_list] == [
        "test-group",
        "test-group.billing",
    ]


async def test_async_consumer_initialize_all_topics_exist_expect_nothing_created(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """필요한 토픽이 모두 있으면 토픽 생성을 요청하지 않는다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())
    admin.list_topics.return_value.topics = {"SampleEvent": 1, "SampleEvent.dlt": 1}

    with (
        patch(f"{WORKER_MODULE}.AIOConsumer") as consumer_cls,
        patch(f"{WORKER_MODULE}.AIOKafkaProducer") as producer_cls,
    ):
        consumer_cls.return_value = AsyncMock()
        producer_cls.return_value = AsyncMock()
        await consumer.initialize_async()

    admin.create_topics.assert_not_called()


async def test_async_consumer_initialize_topic_created_concurrently_expect_tolerated(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """다른 소비자가 먼저 만든 토픽은 실패로 보지 않는다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())
    future = MagicMock()
    future.result.side_effect = KafkaException(
        KafkaError(KafkaError.TOPIC_ALREADY_EXISTS)
    )
    admin.create_topics.return_value = {"SampleEvent": future}

    with (
        patch(f"{WORKER_MODULE}.AIOConsumer") as consumer_cls,
        patch(f"{WORKER_MODULE}.AIOKafkaProducer") as producer_cls,
    ):
        consumer_cls.return_value = AsyncMock()
        producer_cls.return_value = AsyncMock()
        await consumer.initialize_async()

    consumer_cls.return_value.subscribe.assert_awaited_once()


async def test_async_consumer_initialize_topic_creation_refused_expect_error_raised(
    config: KafkaConnectionConfig, admin: MagicMock
) -> None:
    """토픽을 만들 권한이 없으면 구독을 시작하지 않고 시작 단계에서 실패한다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())
    future = MagicMock()
    future.result.side_effect = KafkaException(
        KafkaError(KafkaError.TOPIC_AUTHORIZATION_FAILED)
    )
    admin.create_topics.return_value = {"SampleEvent": future}

    with (
        patch(f"{WORKER_MODULE}.AIOConsumer") as consumer_cls,
        pytest.raises(KafkaException),
    ):
        await consumer.initialize_async()

    consumer_cls.assert_not_called()


async def test_async_consumer_run_failed_subscriber_expect_others_finish_then_error_raised(
    config: KafkaConnectionConfig,
) -> None:
    """한 구독자의 루프가 오류로 끝나도 다른 구독자는 끝까지 돌고, 그 뒤에 오류가 드러난다."""
    consumer = AsyncKafkaEventConsumer(config)
    stop_event = asyncio.Event()
    consumer.set_stop_event(stop_event)
    finished: list[str] = []

    async def failing(received: asyncio.Event) -> None:
        raise RuntimeError("billing loop died")

    async def healthy(received: asyncio.Event) -> None:
        await asyncio.sleep(0)
        assert received is stop_event
        finished.append("shipping")

    consumer.workers = {
        "billing": MagicMock(group_id="test-group.billing", run=failing),
        "shipping": MagicMock(group_id="test-group.shipping", run=healthy),
    }

    with pytest.raises(RuntimeError, match="billing loop died"):
        await consumer.run_async()

    assert finished == ["shipping"]


async def test_async_consumer_run_expect_returns_when_every_subscriber_loop_ends(
    config: KafkaConnectionConfig,
) -> None:
    """모든 구독자의 루프가 정상 종료하면 run도 오류 없이 끝난다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.set_stop_event(asyncio.Event())
    finished: list[str] = []

    async def healthy(received: asyncio.Event) -> None:
        finished.append("unnamed")

    consumer.workers = {None: MagicMock(group_id="test-group", run=healthy)}

    await consumer.run_async()

    assert finished == ["unnamed"]


async def test_async_consumer_dispose_expect_every_worker_closed(
    config: KafkaConnectionConfig,
) -> None:
    """dispose는 모든 구독자의 클라이언트를 닫는다."""
    consumer = AsyncKafkaEventConsumer(config)
    unnamed = AsyncMock()
    billing = AsyncMock()
    consumer.workers = {None: unnamed, "billing": billing}

    await consumer.dispose_async()

    unnamed.close.assert_awaited_once()
    billing.close.assert_awaited_once()


async def test_async_consumer_redrive_expect_routed_to_the_subscriber_worker_only(
    config: KafkaConnectionConfig,
) -> None:
    """비동기 redrive도 지정한 구독자의 worker에만 간다."""
    consumer = AsyncKafkaEventConsumer(config)
    consumer.register(SampleEvent, AsyncMock())
    consumer.register(SampleEvent, AsyncMock(), subscriber="billing")
    billing = AsyncMock()
    billing.redrive.return_value = RedriveResult(succeeded=1, failed=0)
    unnamed = AsyncMock()
    consumer.workers = {None: unnamed, "billing": billing}

    result = await consumer.redrive(SampleEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=1, failed=0)
    billing.redrive.assert_awaited_once_with("SampleEvent", None)
    unnamed.redrive.assert_not_awaited()


async def test_async_consumer_redrive_unregistered_subscription_expect_not_found_error(
    config: KafkaConnectionConfig,
) -> None:
    """등록되지 않은 구독자·이벤트 조합의 redrive는 거절된다."""
    consumer = AsyncKafkaEventConsumer(config)

    with pytest.raises(SubscriptionNotFoundError):
        await consumer.redrive(SampleEvent)
