"""In-memory integration event broker follows the shared delivery contract."""

import threading
from asyncio import Event as AsyncEvent
from asyncio import get_running_loop

import pytest
from pydantic import TypeAdapter
from spakky.auth import AuthVerificationProviderUnavailableError, protected
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.common.mutability import immutable
from spakky.core.pod.annotations.pod import Pod
from spakky.data.aspects.transactional import Transactional
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from unittest.mock import AsyncMock, Mock

from spakky.event.delivery import RetryMode
from spakky.event.error import (
    AbstractNonRetryableEventError,
    EventDeferredError,
    SubscriptionNotFoundError,
)
from spakky.event.event_consumer import (
    IAsyncDomainEventConsumer,
    IAsyncIntegrationEventConsumer,
    IDomainEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.event_publisher import IAsyncEventPublisher, IEventPublisher
from spakky.event.memory import broker as broker_module
from spakky.event.memory import consumer as consumer_module
from spakky.event.memory.broker import InMemoryEventBroker, InMemoryMessage
from spakky.event.memory.config import InMemoryEventConfig
from spakky.event.memory.consumer import (
    AsyncInMemoryEventConsumer,
    InMemoryEventConsumer,
)
from spakky.event.memory.main import initialize
from spakky.event.memory.post_processor import (
    InMemoryProtectedHandlerUnsupportedError,
)
from spakky.event.memory.transport import (
    AsyncInMemoryEventTransport,
    InMemoryEventTransport,
)
from spakky.event.redrive import RedriveResult
from spakky.event.stereotype.event_handler import EventHandler, on_event
from spakky.event.subscription import MixedSubscriptionModeError


@immutable
class OrderPlaced(AbstractIntegrationEvent):
    """An order was placed."""

    order: str


@immutable
class OrderCharged(AbstractIntegrationEvent):
    """An order was charged."""

    order: str


@immutable
class LocalChange(AbstractDomainEvent):
    """A local change the in-memory broker must ignore."""

    value: str


class Permanent(AbstractNonRetryableEventError):
    """A failure no retry can fix."""

    message = "permanent"


@Pod()
def transaction() -> AbstractTransaction:
    """Transaction double required by the publishing aspects."""
    return Mock(spec=AbstractTransaction)


@Pod()
def async_transaction() -> AbstractAsyncTransaction:
    """Async transaction double required by the publishing aspects."""
    return AsyncMock(spec=AbstractAsyncTransaction)


@Pod()
def domain_consumer() -> IDomainEventConsumer:
    """Domain consumer double so a mixed handler class passes provider validation."""
    return Mock(spec=IDomainEventConsumer)


@Pod()
def async_domain_consumer() -> IAsyncDomainEventConsumer:
    """Async domain consumer double for provider validation."""
    return Mock(spec=IAsyncDomainEventConsumer)


class FakeClock:
    """Monotonic clock that only moves when a consumer waits."""

    def __init__(self) -> None:
        self.now = 100.0
        self.waits: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Replace real time in the consumer module."""
    fake = FakeClock()
    monkeypatch.setattr(consumer_module, "monotonic", fake.monotonic)
    monkeypatch.setattr(consumer_module, "sleep", fake.sleep)
    monkeypatch.setattr(consumer_module, "async_sleep", fake.async_sleep)
    return fake


def config(
    monkeypatch: pytest.MonkeyPatch,
    max_attempts: int = 1,
    interval: float = 0.0,
    mode: RetryMode = RetryMode.BLOCKING,
) -> InMemoryEventConfig:
    monkeypatch.setenv("SPAKKY_EVENT_MEMORY__RETRY__MAX_ATTEMPTS", str(max_attempts))
    monkeypatch.setenv("SPAKKY_EVENT_MEMORY__RETRY__INITIAL_INTERVAL", str(interval))
    monkeypatch.setenv("SPAKKY_EVENT_MEMORY__RETRY__MODE", mode.value)
    return InMemoryEventConfig()


def publish(broker: InMemoryEventBroker, event: AbstractIntegrationEvent) -> None:
    InMemoryEventTransport(broker).send(
        event.event_name,
        TypeAdapter(type(event)).dump_json(event),
        {"trace": "t"},
        "key",
    )


def build_app(*pods: type[object]) -> SpakkyApplication:
    app = SpakkyApplication(ApplicationContext()).load_plugins(
        include={
            Plugin(name="spakky-event"),
            Plugin(name="spakky-data"),
            Plugin(name="spakky-tracing"),
        }
    )
    initialize(app)
    app.add(transaction).add(async_transaction)
    for pod in pods:
        app.add(pod)
    return app


async def test_application_flow_expect_each_subscriber_receives_every_event() -> None:
    """브로커 없이도 한 이벤트를 구독자마다 독립적으로 받고, 연쇄 이벤트도 전달된다."""
    seen: list[str] = []

    @EventHandler(subscriber="billing")
    class Billing:
        def __init__(self, publisher: IAsyncEventPublisher) -> None:
            self.publisher = publisher

        @on_event(OrderPlaced)
        async def charge(self, event: OrderPlaced) -> None:
            seen.append(f"billing:{event.order}")
            await self.publisher.publish(OrderCharged(order=event.order))

        @on_event(LocalChange)
        async def local(self, event: LocalChange) -> None: ...

        def helper(self) -> None: ...

    @EventHandler(subscriber="shipping")
    class Shipping:
        @on_event(OrderPlaced)
        def reserve(self, event: OrderPlaced) -> None:
            seen.append(f"shipping:{event.order}")

    @EventHandler()
    class Audit:
        @on_event(OrderCharged)
        def record(self, event: OrderCharged) -> None:
            seen.append(f"audit:{event.order}")

    app = build_app(Billing, Shipping, Audit)
    app.add(domain_consumer).add(async_domain_consumer)
    app.start()
    try:
        broker = app.container.get(InMemoryEventBroker)
        assert isinstance(
            app.container.get(IIntegrationEventConsumer), InMemoryEventConsumer
        )
        assert isinstance(
            app.container.get(IAsyncIntegrationEventConsumer),
            AsyncInMemoryEventConsumer,
        )
        app.container.get(IEventPublisher).publish(OrderPlaced(order="o-1"))
        delivered = await broker.drain_async()
    finally:
        app.stop()

    assert sorted(seen) == ["audit:o-1", "billing:o-1", "shipping:o-1"]
    assert delivered == 3
    assert broker.idle
    assert [message.event_name for message in broker.published] == [
        "OrderPlaced",
        "OrderCharged",
    ]


async def test_advised_handler_expect_registered_and_validated_through_proxy() -> None:
    """AOP가 적용돼 프록시가 된 처리기도 등록에서 빠지지 않는다."""
    seen: list[str] = []

    @EventHandler(subscriber="billing")
    class Billing:
        @on_event(OrderPlaced)
        @Transactional()
        async def charge(self, event: OrderPlaced) -> None:
            seen.append(event.order)

    @EventHandler(subscriber="billing")
    class SyncBilling:
        @on_event(OrderPlaced)
        @Transactional()
        def receipt(self, event: OrderPlaced) -> None: ...

    app = build_app(Billing)
    app.start()
    try:
        broker = app.container.get(InMemoryEventBroker)
        app.container.get(IEventPublisher).publish(OrderPlaced(order="o-1"))
        await broker.drain_async()
    finally:
        app.stop()
    assert seen == ["o-1"]

    with pytest.raises(MixedSubscriptionModeError):
        build_app(Billing, SyncBilling).start()


def test_protected_handler_expect_startup_rejected() -> None:
    """인가가 필요한 처리기는 메모리 브로커가 검증할 수 없어 기동 시 거부한다."""

    @EventHandler(subscriber="billing")
    class Billing:
        @on_event(OrderPlaced)
        @protected
        def charge(self, event: OrderPlaced) -> None: ...

    app = build_app(Billing)
    with pytest.raises(InMemoryProtectedHandlerUnsupportedError) as caught:
        app.start()
    assert caught.value.handler.endswith("Billing.charge")


def test_sync_failure_expect_isolated_retry_dead_letter_and_redrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """실패는 구독자·처리기 단위로 격리되고, dead-letter는 실패한 구독자에게만 다시 들어간다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(broker, config(monkeypatch, max_attempts=2))
    calls: list[str] = []
    broken = True

    def charge(event: OrderPlaced) -> None:
        calls.append("billing.charge")
        if broken:
            raise RuntimeError("card declined")

    consumer.register(OrderPlaced, charge, subscriber="billing", handler_name="charge")
    consumer.register(
        OrderPlaced,
        lambda event: calls.append("billing.receipt"),
        subscriber="billing",
        handler_name="receipt",
    )
    consumer.register(
        OrderPlaced,
        lambda event: calls.append("shipping.reserve"),
        subscriber="shipping",
    )
    publish(broker, OrderPlaced(order="o-1"))

    assert broker.drain() == 3
    assert calls == [
        "billing.charge",
        "billing.receipt",
        "shipping.reserve",
        "billing.charge",
    ]
    assert broker.idle
    assert broker.dead_letters("OrderPlaced", "shipping") == []
    (entry,) = broker.dead_letters("OrderPlaced", "billing")
    assert entry.dead_letter.attempts == 2
    assert entry.dead_letter.pending == frozenset({"charge"})
    assert entry.dead_letter.failures[0].exception_message == "card declined"
    assert entry.message.headers == {"trace": "t"}
    assert entry.message.partition_key == "key"

    calls.clear()
    assert consumer.redrive(OrderPlaced, subscriber="billing") == RedriveResult(
        succeeded=0, failed=1
    )
    broken = False
    assert consumer.redrive(OrderPlaced, subscriber="billing", limit=5) == (
        RedriveResult(succeeded=1, failed=0)
    )
    assert calls == ["billing.charge", "billing.charge"]
    assert broker.dead_letters("OrderPlaced", "billing") == []
    with pytest.raises(SubscriptionNotFoundError):
        consumer.redrive(OrderPlaced, subscriber="audit")


def test_sync_blocking_retry_expect_order_kept_and_delay_waited(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    """순서 유지 모드에서는 재시도 대기 동안 뒤 메시지가 기다린다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(
        broker, config(monkeypatch, max_attempts=2, interval=5.0)
    )
    calls: list[str] = []

    def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        if calls == ["o-1"]:
            raise RuntimeError("first attempt fails")

    consumer.register(OrderPlaced, handle)
    publish(broker, OrderPlaced(order="o-1"))
    publish(broker, OrderPlaced(order="o-2"))

    assert consumer.drain() == 3
    assert calls == ["o-1", "o-1", "o-2"]
    assert clock.waits == [5.0]


def test_sync_delayed_retry_expect_later_messages_pass(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    """지연 재시도 모드에서는 실패한 메시지를 옆으로 두고 뒤 메시지를 먼저 처리한다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(
        broker,
        config(monkeypatch, max_attempts=2, interval=5.0, mode=RetryMode.DELAYED),
    )
    calls: list[str] = []

    def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        if calls == ["o-1"]:
            raise RuntimeError("first attempt fails")

    consumer.register(OrderPlaced, handle)
    publish(broker, OrderPlaced(order="o-1"))
    publish(broker, OrderPlaced(order="o-2"))

    assert consumer.drain() == 3
    assert calls == ["o-1", "o-2", "o-1"]
    assert clock.waits == [5.0]


def test_sync_deferral_and_bad_payload_expect_wait_and_dead_letter(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    """지연 요청은 시도를 세지 않고 기다리며, 역직렬화 불가 본문은 바로 dead-letter다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(broker, config(monkeypatch))
    calls: list[str] = []

    def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        if len(calls) == 1:
            raise EventDeferredError(3.0)

    consumer.register(OrderPlaced, handle, handler_name="handle")
    publish(broker, OrderPlaced(order="o-1"))
    broker.publish(InMemoryMessage(event_name="OrderPlaced", payload=b"{}", headers={}))

    assert consumer.drain() == 3
    assert calls == ["o-1", "o-1"]
    assert clock.waits == [3.0]
    (entry,) = broker.dead_letters("OrderPlaced")
    assert entry.dead_letter.failures[0].handler == "handle"
    assert entry.dead_letter.failures[0].retryable is False
    assert consumer.redrive(OrderPlaced) == RedriveResult(succeeded=0, failed=1)


def test_sync_auth_provider_outage_expect_message_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """판정 없이 끝난 전달은 메시지를 잃지 않고 제자리에 둔다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(broker, config(monkeypatch))

    def handle(event: OrderPlaced) -> None:
        raise AuthVerificationProviderUnavailableError()

    consumer.register(OrderPlaced, handle)
    publish(broker, OrderPlaced(order="o-1"))

    with pytest.raises(AuthVerificationProviderUnavailableError):
        consumer.drain()
    assert len(broker.queued("OrderPlaced")) == 1
    assert not broker.idle


def test_sync_background_run_expect_delivery_until_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """백그라운드 서비스로 돌 때도 도착한 메시지를 전달하고 정지 신호에 멈춘다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(broker, config(monkeypatch))
    stop = threading.Event()
    consumer.set_stop_event(stop)
    calls: list[str] = []

    def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        stop.set()

    consumer.register(OrderPlaced, handle)
    publish(broker, OrderPlaced(order="o-1"))

    consumer.initialize()
    consumer.run()
    consumer.dispose()

    assert calls == ["o-1"]


async def test_async_failure_expect_isolated_retry_dead_letter_and_redrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """비동기 소비자도 실패 격리·dead-letter·다시 넣기 계약을 지킨다."""
    broker = InMemoryEventBroker()
    consumer = AsyncInMemoryEventConsumer(broker, config(monkeypatch, max_attempts=2))
    calls: list[str] = []
    broken = True

    async def charge(event: OrderPlaced) -> None:
        calls.append("billing.charge")
        if broken:
            raise Permanent()

    async def receipt(event: OrderPlaced) -> None:
        calls.append("billing.receipt")

    async def reserve(event: OrderPlaced) -> None:
        calls.append("shipping.reserve")

    consumer.register(OrderPlaced, charge, subscriber="billing", handler_name="charge")
    consumer.register(
        OrderPlaced, receipt, subscriber="billing", handler_name="receipt"
    )
    consumer.register(OrderPlaced, reserve, subscriber="shipping")
    await AsyncInMemoryEventTransport(broker).send(
        "OrderPlaced", TypeAdapter(OrderPlaced).dump_json(OrderPlaced(order="o-1")), {}
    )
    await AsyncInMemoryEventTransport(broker).flush()
    InMemoryEventTransport(broker).flush()

    assert await consumer.drain_async() == 2
    assert calls == ["billing.charge", "billing.receipt", "shipping.reserve"]
    (entry,) = broker.dead_letters("OrderPlaced", "billing")
    assert entry.dead_letter.attempts == 1
    assert entry.dead_letter.pending == frozenset({"charge"})

    calls.clear()
    assert await consumer.redrive(OrderPlaced, subscriber="billing") == (
        RedriveResult(succeeded=0, failed=1)
    )
    broken = False
    assert await consumer.redrive(OrderPlaced, subscriber="billing", limit=1) == (
        RedriveResult(succeeded=1, failed=0)
    )
    assert calls == ["billing.charge", "billing.charge"]


@pytest.mark.parametrize(
    "mode, expected",
    [
        (RetryMode.BLOCKING, ["o-1", "o-1", "o-2"]),
        (RetryMode.DELAYED, ["o-1", "o-2", "o-1"]),
    ],
)
async def test_async_retry_modes_expect_order_kept_or_given_up(
    monkeypatch: pytest.MonkeyPatch,
    clock: FakeClock,
    mode: RetryMode,
    expected: list[str],
) -> None:
    """비동기 소비자도 재시도 모드에 따라 순서를 지키거나 포기한다."""
    broker = InMemoryEventBroker()
    consumer = AsyncInMemoryEventConsumer(
        broker, config(monkeypatch, max_attempts=2, interval=5.0, mode=mode)
    )
    calls: list[str] = []

    async def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        if calls == ["o-1"]:
            raise RuntimeError("first attempt fails")

    consumer.register(OrderPlaced, handle)
    publish(broker, OrderPlaced(order="o-1"))
    publish(broker, OrderPlaced(order="o-2"))

    assert await consumer.drain_async() == 3
    assert calls == expected
    assert clock.waits == [5.0]


async def test_async_deferral_bad_payload_and_outage_expect_same_contract(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    """비동기 소비자도 지연·역직렬화 실패·판정 없는 장애를 같은 방식으로 다룬다."""
    broker = InMemoryEventBroker()
    consumer = AsyncInMemoryEventConsumer(broker, config(monkeypatch))
    calls: list[str] = []

    async def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        if len(calls) == 1:
            raise EventDeferredError(3.0)
        if event.order == "outage":
            raise AuthVerificationProviderUnavailableError()

    consumer.register(OrderPlaced, handle, handler_name="handle")
    publish(broker, OrderPlaced(order="o-1"))
    broker.publish(InMemoryMessage(event_name="OrderPlaced", payload=b"{}", headers={}))

    assert await consumer.drain_async() == 3
    assert clock.waits == [3.0]
    assert len(broker.dead_letters("OrderPlaced")) == 1

    publish(broker, OrderPlaced(order="outage"))
    with pytest.raises(AuthVerificationProviderUnavailableError):
        await consumer.drain_async()
    assert len(broker.queued("OrderPlaced")) == 1


async def test_async_background_run_expect_delivery_until_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """비동기 백그라운드 서비스도 메시지를 전달하고 정지 신호에 멈춘다."""
    monkeypatch.setenv("SPAKKY_EVENT_MEMORY__POLL_INTERVAL", "0.001")
    broker = InMemoryEventBroker()
    consumer = AsyncInMemoryEventConsumer(broker, config(monkeypatch))
    stop = AsyncEvent()
    consumer.set_stop_event(stop)
    calls: list[str] = []

    async def handle(event: OrderPlaced) -> None:
        calls.append(event.order)
        if len(calls) == 2:
            stop.set()
        else:
            # 빈 큐에서 한 번 이상 poll 대기가 끝난 뒤 다음 메시지가 도착한다.
            get_running_loop().call_later(
                0.01, publish, broker, OrderPlaced(order="o-2")
            )

    consumer.register(OrderPlaced, handle)
    publish(broker, OrderPlaced(order="o-1"))

    await consumer.initialize_async()
    await consumer.run_async()
    await consumer.dispose_async()

    assert calls == ["o-1", "o-2"]


def test_broker_without_subscribers_expect_published_log_only() -> None:
    """구독자가 없는 이벤트는 발행 기록에만 남는다."""
    broker = InMemoryEventBroker()
    publish(broker, OrderPlaced(order="o-1"))
    assert len(broker.published) == 1
    assert broker.queued("OrderPlaced") == []
    assert broker.dead_letters("OrderPlaced") == []
    assert broker.idle
    assert broker.drain() == 0


async def test_drain_with_message_in_flight_expect_waits_until_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """백그라운드 소비자가 처리 중인 메시지가 끝날 때까지 drain이 기다린다."""
    broker = InMemoryEventBroker()
    broker.bind(("OrderPlaced", None))
    waits: list[float] = []

    def settle(seconds: float) -> None:
        waits.append(seconds)
        broker.done(("OrderPlaced", None))

    async def settle_async(seconds: float) -> None:
        settle(seconds)

    monkeypatch.setattr(broker_module, "sleep", settle)
    monkeypatch.setattr(broker_module, "async_sleep", settle_async)

    publish(broker, OrderPlaced(order="o-1"))
    assert broker.take(("OrderPlaced", None), 0.0, True) is not None
    publish(broker, OrderPlaced(order="behind"))
    assert broker.take(("OrderPlaced", None), 0.0, True) is None
    assert broker.next_due_in([("OrderPlaced", None)], 0.0, True) is None
    assert broker.drain() == 0
    assert broker.take(("OrderPlaced", None), 0.0, True) is not None
    broker.done(("OrderPlaced", None))

    publish(broker, OrderPlaced(order="o-2"))
    assert broker.take(("OrderPlaced", None), 0.0, True) is not None
    assert await broker.drain_async() == 0

    assert waits == [broker_module.IN_FLIGHT_POLL_INTERVAL] * 2
    assert broker.idle


def test_redrive_partial_failure_expect_dead_letter_narrowed_to_failed_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """다시 넣기에서 성공한 처리기는 메타데이터에서 빠져 다음에 다시 실행되지 않는다."""
    broker = InMemoryEventBroker()
    consumer = InMemoryEventConsumer(broker, config(monkeypatch))
    calls: list[str] = []
    errors: dict[str, Exception] = {
        "a": RuntimeError("a"),
        "b": RuntimeError("b"),
        "c": RuntimeError("c"),
    }

    def handler(name: str):
        def handle(event: OrderPlaced) -> None:
            calls.append(name)
            if name in errors:
                raise errors[name]

        return handle

    for name in ("a", "b", "c"):
        consumer.register(OrderPlaced, handler(name), handler_name=name)
    publish(broker, OrderPlaced(order="o-1"))
    consumer.drain()

    del errors["a"]
    assert consumer.redrive(OrderPlaced).failed == 1
    (entry,) = broker.dead_letters("OrderPlaced")
    assert entry.dead_letter.pending == frozenset({"b", "c"})

    errors["b"] = EventDeferredError(1.0)
    del errors["c"]
    calls.clear()
    assert consumer.redrive(OrderPlaced).failed == 1
    assert calls == ["b", "c"]
    (entry,) = broker.dead_letters("OrderPlaced")
    assert entry.dead_letter.pending == frozenset({"b"})

    monkeypatch.setenv("SPAKKY_EVENT_MEMORY__RETRY__MAX_ATTEMPTS", "2")
    retrying = InMemoryEventConsumer(broker, InMemoryEventConfig())
    retrying.register(OrderPlaced, handler("b"), handler_name="b")
    errors["b"] = RuntimeError("again")
    assert retrying.redrive(OrderPlaced).failed == 1
    (entry,) = broker.dead_letters("OrderPlaced")
    assert entry.dead_letter.failures[0].exception_message == "again"
