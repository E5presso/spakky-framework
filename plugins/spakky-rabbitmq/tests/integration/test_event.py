from asyncio import Event as AsyncEvent
from asyncio import sleep as asleep  # type: ignore[attr-defined] - compatibility alias used by integration test
from collections.abc import Callable
from threading import Event
from time import sleep, time
from unittest.mock import MagicMock

import pytest
from pika import BlockingConnection, URLParameters
from pydantic import TypeAdapter
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.transaction import AbstractTransaction
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.delivery import DeadLetter, EventDeliveryContext, EventRouting
from spakky.event.event_publisher import (
    IAsyncEventTransport,
    IEventTransport,
)
from spakky.event.redrive import IAsyncEventRedriver, RedriveResult

from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig
from spakky.plugins.rabbitmq.common.constants import RABBITMQ_CONFIG_ENV_PREFIX
from spakky.plugins.rabbitmq.error import SubscriberExchangeRequiredError
from spakky.plugins.rabbitmq.event.consumer import (
    AsyncRabbitMQEventConsumer,
    RabbitMQEventConsumer,
)
from spakky.plugins.rabbitmq.event.topology import RabbitMQSubscriptionQueues
from spakky.plugins.rabbitmq.event.transport import (
    AsyncRabbitMQEventTransport,
    RabbitMQEventTransport,
)
from tests.apps.dummy import (
    AsyncBlockingRetryEvent,
    AsyncEventHandler,
    AsyncTestEvent,
    AuditPoisonHandler,
    BillingFanoutHandler,
    BlockingRetryEvent,
    BrokenPoisonHandler,
    DelayedDeadLetterEvent,
    DelayedRetryEvent,
    DummyEventHandler,
    FanoutEvent,
    PoisonEvent,
    SampleEvent,
    ShippingFanoutHandler,
    SyncRedriveEvent,
)

POLL_INTERVAL = 0.05  # seconds between checks
MAX_WAIT_TIME = 10  # maximum seconds to wait

_sample_event_type_adapter: TypeAdapter[SampleEvent] = TypeAdapter(SampleEvent)
_async_event_type_adapter: TypeAdapter[AsyncTestEvent] = TypeAdapter(AsyncTestEvent)


def wait_for_count(
    handler: DummyEventHandler | AsyncEventHandler, expected: int
) -> None:
    """Poll until handler.count reaches expected value or timeout."""
    start = time()
    while handler.count < expected:
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError(
                f"Timed out waiting for handler.count to reach {expected}. "
                f"Current count: {handler.count}"
            )
        sleep(POLL_INTERVAL)


def wait_until(condition: Callable[[], bool]) -> None:
    """Poll until the condition holds or the bounded wait runs out."""
    start = time()
    while not condition():
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError("Timed out waiting for the expected broker state.")
        sleep(POLL_INTERVAL)


async def async_wait_until(condition: Callable[[], bool]) -> None:
    """Async poll until the condition holds or the bounded wait runs out."""
    start = time()
    while not condition():
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError("Timed out waiting for the expected broker state.")
        await asleep(POLL_INTERVAL)


def payload_of(event: AbstractIntegrationEvent) -> bytes:
    """Serialize an event the way the event bus hands it to a transport."""
    return TypeAdapter(type(event)).dump_json(event)


def queue_depth(config: RabbitMQConnectionConfig, queue: str) -> int:
    """Return the number of ready messages in an existing queue."""
    connection = BlockingConnection(URLParameters(config.connection_string))
    try:
        declared = connection.channel().queue_declare(queue, passive=True)
        return declared.method.message_count or 0
    finally:
        connection.close()


def peek_dead_letter(config: RabbitMQConnectionConfig, queue: str) -> DeadLetter:
    """Read the metadata of the first dead letter and leave it in the queue."""
    connection = BlockingConnection(URLParameters(config.connection_string))
    try:
        channel = connection.channel()
        start = time()
        while True:
            _, properties, _ = channel.basic_get(queue)
            if properties is not None:
                return DeadLetter.from_headers(
                    RabbitMQEventConsumer._to_string_headers(properties.headers)
                )
            if time() - start > MAX_WAIT_TIME:
                raise TimeoutError(f"Timed out waiting for a dead letter in {queue}.")
            sleep(POLL_INTERVAL)
    finally:
        # 확인하지 않고 닫으면 브로커가 메시지를 큐에 되돌린다.
        connection.close()


def retry_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
    max_attempts: int,
    initial_interval: float = 0.05,
) -> RabbitMQConnectionConfig:
    """Build a config whose retry policy differs from the shared application."""
    monkeypatch.setenv(f"{RABBITMQ_CONFIG_ENV_PREFIX}RETRY__MODE", mode)
    monkeypatch.setenv(
        f"{RABBITMQ_CONFIG_ENV_PREFIX}RETRY__MAX_ATTEMPTS", str(max_attempts)
    )
    monkeypatch.setenv(
        f"{RABBITMQ_CONFIG_ENV_PREFIX}RETRY__INITIAL_INTERVAL", str(initial_interval)
    )
    monkeypatch.setenv(f"{RABBITMQ_CONFIG_ENV_PREFIX}DECLARE_DEFAULT_QUEUE", "false")
    return RabbitMQConnectionConfig()


async def async_wait_for_count(
    handler: DummyEventHandler | AsyncEventHandler, expected: int
) -> None:
    """Async poll until handler.count reaches expected value or timeout."""
    start = time()
    while handler.count < expected:
        if time() - start > MAX_WAIT_TIME:
            raise TimeoutError(
                f"Timed out waiting for handler.count to reach {expected}. "
                f"Current count: {handler.count}"
            )
        await asleep(POLL_INTERVAL)


def test_synchronous_event(app: SpakkyApplication) -> None:
    """동기 이벤트 발행 및 핸들링이 올바르게 동작하는지 검증한다."""
    transport = app.container.get(IEventTransport)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    event1 = SampleEvent(message="Hello, World!")
    event2 = SampleEvent(message="Goodbye, World!")
    transport.send("SampleEvent", _sample_event_type_adapter.dump_json(event1), {})
    transport.send("SampleEvent", _sample_event_type_adapter.dump_json(event2), {})
    wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2


@pytest.mark.asyncio
async def test_asynchronous_event(app: SpakkyApplication) -> None:
    """비동기 이벤트 발행 및 핸들링이 올바르게 동작하는지 검증한다."""
    transport = app.container.get(IAsyncEventTransport)
    handler = app.container.get(DummyEventHandler)
    initial_count = handler.count
    event1 = SampleEvent(message="Hello, World!")
    event2 = SampleEvent(message="Goodbye, World!")
    await transport.send(
        "SampleEvent", _sample_event_type_adapter.dump_json(event1), {}
    )
    await transport.send(
        "SampleEvent", _sample_event_type_adapter.dump_json(event2), {}
    )
    await async_wait_for_count(handler, initial_count + 2)
    assert handler.count == initial_count + 2


@pytest.mark.asyncio
async def test_async_handler_execution(app: SpakkyApplication) -> None:
    """비동기 컨슈머를 통한 비동기 이벤트 핸들러 실행을 검증한다."""
    transport = app.container.get(IAsyncEventTransport)
    handler = app.container.get(AsyncEventHandler)

    initial_count = handler.count
    event1 = AsyncTestEvent(message="Test1")
    event2 = AsyncTestEvent(message="Test2")
    event3 = AsyncTestEvent(message="Test3")
    await transport.send(
        "AsyncTestEvent", _async_event_type_adapter.dump_json(event1), {}
    )
    await transport.send(
        "AsyncTestEvent", _async_event_type_adapter.dump_json(event2), {}
    )
    await transport.send(
        "AsyncTestEvent", _async_event_type_adapter.dump_json(event3), {}
    )
    await async_wait_for_count(handler, initial_count + 3)

    # All async events should be handled
    assert handler.count == initial_count + 3


def test_named_subscribers_expect_each_receives_every_message(
    app: SpakkyApplication,
) -> None:
    """이름 있는 두 구독자가 같은 이벤트의 모든 메시지를 각자 받는지 검증한다 (한쪽은 AOP proxy)."""
    transport = app.container.get(IEventTransport)
    billing = app.container.get(BillingFanoutHandler)
    shipping = app.container.get(ShippingFanoutHandler)

    transport.send("FanoutEvent", payload_of(FanoutEvent(message="first")), {})
    transport.send("FanoutEvent", payload_of(FanoutEvent(message="second")), {})

    wait_until(lambda: len(billing.messages) == 2 and len(shipping.messages) == 2)
    assert billing.messages == ["first", "second"]
    assert shipping.messages == ["first", "second"]
    # billing 핸들러는 @Transactional이 적용된 AOP proxy인데도 등록되어 실행된다.
    transaction_double = app.container.get(AbstractTransaction)
    assert isinstance(transaction_double, MagicMock)
    assert transaction_double.__enter__.call_count == 2


@pytest.mark.asyncio
async def test_failing_subscriber_expect_own_dead_letter_and_isolated_redrive(
    app: SpakkyApplication,
) -> None:
    """실패한 구독자만 자신의 dlq로 보내고, redrive가 실패한 핸들러만 다시 실행하는지 검증한다."""
    config = app.container.get(RabbitMQConnectionConfig)
    transport = app.container.get(IAsyncEventTransport)
    redriver = app.container.get(IAsyncEventRedriver)
    audit = app.container.get(AuditPoisonHandler)
    broken = app.container.get(BrokenPoisonHandler)
    queues = RabbitMQSubscriptionQueues.of("PoisonEvent", "broken")

    await transport.send("PoisonEvent", payload_of(PoisonEvent(message="order")), {})

    # 한 구독자의 실패가 다른 구독자와 같은 구독자의 다른 핸들러를 막지 않는다.
    await async_wait_until(
        lambda: audit.messages == ["order"] and broken.notified == ["order"]
    )
    dead_letter = peek_dead_letter(config, queues.dead_letter_queue)
    assert dead_letter.event_name == "PoisonEvent"
    assert dead_letter.subscriber == "broken"
    assert dead_letter.attempts == 1
    assert [failure.handler for failure in dead_letter.failures] == [
        "BrokenPoisonHandler.project"
    ]
    assert dead_letter.failures[0].exception_type == "BrokenProjectionError"
    assert dead_letter.failures[0].retryable is True
    assert queue_depth(config, "PoisonEvent.audit.dlq") == 0

    # 아직 고쳐지지 않았으면 redrive해도 dlq에 남는다.
    still_failing = await redriver.redrive(PoisonEvent, subscriber="broken")
    assert still_failing == RedriveResult(succeeded=0, failed=1)
    assert broken.projection_calls == 2
    await async_wait_until(lambda: queue_depth(config, queues.dead_letter_queue) == 1)

    broken.healthy = True
    redriven = await redriver.redrive(PoisonEvent, subscriber="broken")

    assert redriven == RedriveResult(succeeded=1, failed=0)
    assert broken.projected == ["order"]
    assert broken.projection_calls == 3
    # 실패하지 않았던 핸들러와 다른 구독자는 다시 실행되지 않는다.
    assert broken.notified == ["order"]
    assert audit.messages == ["order"]
    assert queue_depth(config, queues.dead_letter_queue) == 0


def test_sync_blocking_retry_expect_only_failed_handler_reruns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BLOCKING 재시도가 성공하지 못한 핸들러만 다시 실행하는지 검증한다."""
    config = retry_config(monkeypatch, mode="blocking", max_attempts=3)
    consumer = RabbitMQEventConsumer(config)
    flaky_attempts: list[int] = []
    steady_calls: list[str] = []

    def flaky(event: BlockingRetryEvent) -> None:
        flaky_attempts.append(EventDeliveryContext.current().attempt)
        if len(flaky_attempts) < 3:
            raise ConnectionError("downstream is not ready")

    def steady(event: BlockingRetryEvent) -> None:
        steady_calls.append(event.message)

    consumer.register(
        BlockingRetryEvent, flaky, subscriber="retrying", handler_name="flaky"
    )
    consumer.register(
        BlockingRetryEvent, steady, subscriber="retrying", handler_name="steady"
    )
    consumer.set_stop_event(Event())
    consumer.start()
    try:
        RabbitMQEventTransport(config).send(
            "BlockingRetryEvent", payload_of(BlockingRetryEvent(message="once")), {}
        )
        wait_until(lambda: len(flaky_attempts) == 3)
    finally:
        consumer.stop()

    assert flaky_attempts == [1, 2, 3]
    assert steady_calls == ["once"]
    assert queue_depth(config, "BlockingRetryEvent.retrying") == 0
    assert queue_depth(config, "BlockingRetryEvent.retrying.dlq") == 0


@pytest.mark.asyncio
async def test_async_blocking_retry_expect_only_failed_handler_reruns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """비동기 BLOCKING 재시도가 성공하지 못한 핸들러만 다시 실행하는지 검증한다."""
    config = retry_config(monkeypatch, mode="blocking", max_attempts=2)
    consumer = AsyncRabbitMQEventConsumer(config)
    flaky_attempts: list[int] = []
    steady_calls: list[str] = []

    async def flaky(event: AsyncBlockingRetryEvent) -> None:
        flaky_attempts.append(EventDeliveryContext.current().attempt)
        if len(flaky_attempts) < 2:
            raise ConnectionError("downstream is not ready")

    async def steady(event: AsyncBlockingRetryEvent) -> None:
        steady_calls.append(event.message)

    consumer.register(
        AsyncBlockingRetryEvent, flaky, subscriber="retrying", handler_name="flaky"
    )
    consumer.register(
        AsyncBlockingRetryEvent, steady, subscriber="retrying", handler_name="steady"
    )
    consumer.set_stop_event(AsyncEvent())
    await consumer.start_async()
    try:
        await AsyncRabbitMQEventTransport(config).send(
            "AsyncBlockingRetryEvent",
            payload_of(AsyncBlockingRetryEvent(message="once")),
            {},
        )
        await async_wait_until(lambda: len(flaky_attempts) == 2)
    finally:
        await consumer.stop_async()

    assert flaky_attempts == [1, 2]
    assert steady_calls == ["once"]
    assert queue_depth(config, "AsyncBlockingRetryEvent.retrying.dlq") == 0


@pytest.mark.asyncio
async def test_async_delayed_retry_expect_wait_queue_returns_to_own_subscriber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELAYED 재시도가 대기 큐를 거쳐 실패한 구독자에게만 돌아오는지 검증한다."""
    config = retry_config(
        monkeypatch, mode="delayed", max_attempts=2, initial_interval=0.2
    )
    consumer = AsyncRabbitMQEventConsumer(config)
    flaky_attempts: list[int] = []
    steady_calls: list[str] = []
    other_calls: list[str] = []

    async def flaky(event: DelayedRetryEvent) -> None:
        flaky_attempts.append(EventDeliveryContext.current().attempt)
        if len(flaky_attempts) < 2:
            raise ConnectionError("downstream is not ready")

    async def steady(event: DelayedRetryEvent) -> None:
        steady_calls.append(event.message)

    async def other(event: DelayedRetryEvent) -> None:
        other_calls.append(event.message)

    consumer.register(
        DelayedRetryEvent, flaky, subscriber="retrying", handler_name="flaky"
    )
    consumer.register(
        DelayedRetryEvent, steady, subscriber="retrying", handler_name="steady"
    )
    consumer.register(
        DelayedRetryEvent, other, subscriber="other", handler_name="other"
    )
    consumer.set_stop_event(AsyncEvent())
    await consumer.start_async()
    try:
        await AsyncRabbitMQEventTransport(config).send(
            "DelayedRetryEvent", payload_of(DelayedRetryEvent(message="once")), {}
        )
        await async_wait_until(lambda: len(flaky_attempts) == 2)
        await async_wait_until(lambda: other_calls == ["once"])
    finally:
        await consumer.stop_async()

    # 재시도 상태가 메시지 헤더로 전달되어 두 번째 시도로 실행된다.
    assert flaky_attempts == [1, 2]
    assert steady_calls == ["once"]
    # 대기 큐는 exchange가 아니라 구독자 큐로만 되돌리므로 다른 구독자는 한 번만 받는다.
    assert other_calls == ["once"]
    assert queue_depth(config, "DelayedRetryEvent.retrying.retry") == 0
    assert queue_depth(config, "DelayedRetryEvent.retrying.dlq") == 0


def test_sync_delayed_retry_exhausted_expect_dead_letter_with_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELAYED 재시도를 모두 소진한 메시지가 시도 횟수와 함께 dlq로 가는지 검증한다."""
    config = retry_config(monkeypatch, mode="delayed", max_attempts=2)
    consumer = RabbitMQEventConsumer(config)
    attempts: list[int] = []

    def always_fails(event: DelayedDeadLetterEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        raise ConnectionError("downstream never recovers")

    consumer.register(
        DelayedDeadLetterEvent,
        always_fails,
        subscriber="retrying",
        handler_name="always_fails",
    )
    consumer.set_stop_event(Event())
    consumer.start()
    try:
        RabbitMQEventTransport(config).send(
            "DelayedDeadLetterEvent",
            payload_of(DelayedDeadLetterEvent(message="once")),
            {},
        )
        dead_letter = peek_dead_letter(config, "DelayedDeadLetterEvent.retrying.dlq")
    finally:
        consumer.stop()

    assert attempts == [1, 2]
    assert dead_letter.attempts == 2
    assert dead_letter.subscriber == "retrying"
    assert dead_letter.pending == frozenset({"always_fails"})


def test_sync_redrive_expect_failed_handler_reruns_and_dead_letter_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """동기 redrive가 실패했던 핸들러만 다시 실행하고 성공한 dead letter를 지우는지 검증한다."""
    config = retry_config(monkeypatch, mode="blocking", max_attempts=1)
    consumer = RabbitMQEventConsumer(config)
    healthy: list[bool] = []
    projected: list[str] = []
    notified: list[str] = []

    def project(event: SyncRedriveEvent) -> None:
        if not healthy:
            raise ConnectionError("projection store is down")
        projected.append(event.message)

    def notify(event: SyncRedriveEvent) -> None:
        notified.append(event.message)

    consumer.register(
        SyncRedriveEvent, project, subscriber="projection", handler_name="project"
    )
    consumer.register(
        SyncRedriveEvent, notify, subscriber="projection", handler_name="notify"
    )
    queue = "SyncRedriveEvent.projection.dlq"
    consumer.set_stop_event(Event())
    consumer.start()
    try:
        RabbitMQEventTransport(config).send(
            "SyncRedriveEvent", payload_of(SyncRedriveEvent(message="once")), {}
        )
        assert peek_dead_letter(config, queue).pending == frozenset({"project"})
        wait_until(lambda: queue_depth(config, queue) == 1)

        still_failing = consumer.redrive(SyncRedriveEvent, subscriber="projection")
        wait_until(lambda: queue_depth(config, queue) == 1)
        healthy.append(True)
        redriven = consumer.redrive(SyncRedriveEvent, subscriber="projection", limit=5)
    finally:
        consumer.stop()

    assert still_failing == RedriveResult(succeeded=0, failed=1)
    assert redriven == RedriveResult(succeeded=1, failed=0)
    assert projected == ["once"]
    assert notified == ["once"]
    assert queue_depth(config, queue) == 0


def test_named_subscriber_without_exchange_expect_startup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """exchange 없이 이름 있는 구독자를 등록하면 시작 단계에서 실패하는지 검증한다."""
    monkeypatch.delenv(f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME")
    config = RabbitMQConnectionConfig()

    def handler(event: FanoutEvent) -> None:
        return None

    with pytest.raises(SubscriberExchangeRequiredError) as raised:
        RabbitMQEventConsumer(config).register(
            FanoutEvent, handler, subscriber="billing"
        )

    assert raised.value.subscriber == "billing"
    assert EventRouting.name_of(raised.value.event_type) == "FanoutEvent"
