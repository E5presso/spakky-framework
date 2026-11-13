"""Unit tests for the asynchronous RabbitMQ consumer.

The broker is replaced by mocks; every test drives the consumer through the
callback it registers with `queue.consume`, exactly as aio-pika would.
"""

from asyncio import Event
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import override
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aio_pika import DeliveryMode, Message
from aio_pika.exceptions import DeliveryError
from spakky.auth import (
    AuthorizationDecision,
    AuthorizationReasonCode,
    AuthRequirementDeniedError,
    AuthVerificationProviderUnavailableError,
)
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.delivery import (
    DeadLetter,
    DeadLetterHeader,
    DeliveryHeader,
    DeliveryState,
    EventDeliveryContext,
    HandlerFailure,
)
from spakky.event.error import (
    AbstractNonRetryableEventError,
    EventDeferredError,
    InvalidMessageError,
    SubscriptionNotFoundError,
)
from spakky.event.redrive import RedriveResult
from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.rabbitmq.auth import current_rabbitmq_message_headers
from spakky.plugins.rabbitmq.common.config import RabbitMQConnectionConfig
from spakky.plugins.rabbitmq.common.constants import RABBITMQ_CONFIG_ENV_PREFIX
from spakky.plugins.rabbitmq.error import SubscriberExchangeRequiredError
from spakky.plugins.rabbitmq.event.consumer import AsyncRabbitMQEventConsumer

CONNECT = "spakky.plugins.rabbitmq.event.consumer.connect_robust"
BODY = b'{"data": "test"}'
SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"

type MessageCallback = Callable[[AsyncMock], Awaitable[None]]


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Sample integration event for testing."""

    data: str


@immutable
class RenamedIntegrationEvent(AbstractIntegrationEvent):
    """Integration event with custom outbound routing identity."""

    data: str

    @property
    @override
    def event_name(self) -> str:
        return "external.renamed.v1"


class PermanentFailureError(AbstractNonRetryableEventError):
    """Handler failure another attempt cannot fix."""

    message = "permanent failure"


class Broker:
    """Mocked connection, channels and queues a started consumer talks to."""

    connection: AsyncMock
    channel: AsyncMock
    publish_channel: AsyncMock
    exchange: AsyncMock
    queues: dict[str, AsyncMock]
    declared: dict[str, dict[str, object]]

    def __init__(self) -> None:
        self.connection = AsyncMock()
        self.channel = AsyncMock()
        self.publish_channel = AsyncMock()
        self.exchange = AsyncMock()
        self.queues = {}
        self.declared = {}
        self.connection.channel = AsyncMock(
            side_effect=[self.channel, self.publish_channel]
        )
        self.channel.declare_exchange = AsyncMock(return_value=self.exchange)
        self.channel.declare_queue = AsyncMock(side_effect=self._declare_queue)

    def _declare_queue(self, name: str, **options: object) -> AsyncMock:
        self.declared[name] = options
        return self.queues.setdefault(name, AsyncMock())

    def callback(self, queue: str) -> MessageCallback:
        """Return the callback the consumer registered for a queue."""
        return self.queues[queue].consume.call_args.args[0]

    async def deliver(
        self,
        queue: str,
        *,
        body: bytes = BODY,
        headers: dict[str, object] | None = None,
    ) -> AsyncMock:
        """Hand one message to the consumer as aio-pika would."""
        message = incoming(body, headers)
        await self.callback(queue)(message)
        return message

    def published(self) -> tuple[str, Message]:
        """Return queue and message of the single forwarded copy."""
        publish = self.publish_channel.default_exchange.publish
        assert publish.call_count == 1
        return publish.call_args.kwargs["routing_key"], publish.call_args.args[0]


def incoming(body: bytes = BODY, headers: dict[str, object] | None = None) -> AsyncMock:
    """Build an incoming message with settable ack/nack."""
    message = AsyncMock()
    message.consumer_tag = "ctag"
    message.delivery_tag = 7
    message.headers = headers
    message.body = body
    return message


def make_config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exchange: str | None = "test_exchange",
    **settings: str,
) -> RabbitMQConnectionConfig:
    """Build a config from environment variables, as an application would."""
    values = {
        "USE_SSL": "false",
        "HOST": "localhost",
        "PORT": "5672",
        "USER": "guest",
        "PASSWORD": "guest",
        **settings,
    }
    monkeypatch.delenv(f"{RABBITMQ_CONFIG_ENV_PREFIX}EXCHANGE_NAME", raising=False)
    if exchange is not None:
        values["EXCHANGE_NAME"] = exchange
    for key, value in values.items():
        monkeypatch.setenv(f"{RABBITMQ_CONFIG_ENV_PREFIX}{key}", value)
    return RabbitMQConnectionConfig()


async def start(consumer: AsyncRabbitMQEventConsumer) -> Broker:
    """Initialize the consumer against a mocked broker."""
    broker = Broker()
    consumer.set_stop_event(Event())
    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        await consumer.initialize_async()
    return broker


@pytest.mark.asyncio
async def test_async_initialize_unnamed_blocking_expect_event_queue_bound_with_prefetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이름 없는 구독자는 이벤트 이름 큐를 쓰고 BLOCKING 모드에서 prefetch 1을 건다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, AsyncMock())

    broker = await start(consumer)

    assert broker.connection.channel.call_args_list[1].kwargs == {
        "on_return_raises": True
    }
    broker.channel.set_qos.assert_called_once_with(prefetch_count=1)
    broker.channel.declare_exchange.assert_called_once_with("test_exchange")
    assert broker.declared == {
        "SampleIntegrationEvent": {"durable": True},
        "SampleIntegrationEvent.dlq": {"durable": True},
    }
    broker.queues["SampleIntegrationEvent"].bind.assert_called_once_with(
        broker.exchange, "SampleIntegrationEvent"
    )
    broker.queues["SampleIntegrationEvent"].consume.assert_called_once()


@pytest.mark.asyncio
async def test_async_initialize_named_delayed_expect_own_queue_and_wait_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이름 있는 구독자는 자신의 큐·dlq·대기 큐를 갖고 대기 큐는 자기 큐로만 되돌린다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MODE="delayed")
    )
    consumer.register(RenamedIntegrationEvent, AsyncMock(), subscriber="billing")

    broker = await start(consumer)

    broker.channel.set_qos.assert_not_called()
    assert broker.declared == {
        "external.renamed.v1.billing": {"durable": True},
        "external.renamed.v1.billing.dlq": {"durable": True},
        "external.renamed.v1.billing.retry": {
            "durable": True,
            "arguments": {
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "external.renamed.v1.billing",
            },
        },
    }
    broker.queues["external.renamed.v1.billing"].bind.assert_called_once_with(
        broker.exchange, "external.renamed.v1"
    )


@pytest.mark.asyncio
async def test_async_initialize_without_exchange_expect_no_exchange_or_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """exchange가 없으면 기본 exchange에 맡기고 선언·바인딩을 하지 않는다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch, exchange=None))
    consumer.register(SampleIntegrationEvent, AsyncMock())

    broker = await start(consumer)

    broker.channel.declare_exchange.assert_not_called()
    broker.queues["SampleIntegrationEvent"].bind.assert_not_called()
    broker.queues["SampleIntegrationEvent"].consume.assert_called_once()


def test_async_register_named_subscriber_without_exchange_expect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """exchange 없이 이름 있는 구독자를 등록하면 전용 에러로 실패한다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch, exchange=None))

    with pytest.raises(SubscriberExchangeRequiredError) as raised:
        consumer.register(SampleIntegrationEvent, AsyncMock(), subscriber="billing")

    assert raised.value.subscriber == "billing"
    assert raised.value.event_type is SampleIntegrationEvent


@pytest.mark.asyncio
@pytest.mark.parametrize(("consumer_tag", "delivery_tag"), [(None, 1), ("ctag", None)])
async def test_async_message_without_tags_expect_invalid_message_error(
    monkeypatch: pytest.MonkeyPatch,
    consumer_tag: str | None,
    delivery_tag: int | None,
) -> None:
    """consumer tag나 delivery tag가 없는 메시지는 InvalidMessageError로 거부한다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, AsyncMock())
    broker = await start(consumer)
    message = incoming()
    message.consumer_tag = consumer_tag
    message.delivery_tag = delivery_tag

    with pytest.raises(InvalidMessageError):
        await broker.callback("SampleIntegrationEvent")(message)


@pytest.mark.asyncio
async def test_async_message_all_handlers_succeed_expect_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """모든 핸들러가 성공하면 메시지를 ack한다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    first, second = AsyncMock(), AsyncMock()
    consumer.register(SampleIntegrationEvent, first)
    consumer.register(SampleIntegrationEvent, second)
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    assert first.call_args.args[0].data == "test"
    second.assert_awaited_once()
    message.ack.assert_awaited_once_with()
    broker.publish_channel.default_exchange.publish.assert_not_called()


@pytest.mark.asyncio
async def test_async_message_headers_expect_decoded_strings_visible_to_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bytes 헤더는 문자열로 풀리고 문자열이 아닌 값은 빠진 채 핸들러에 보인다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    seen: list[dict[str, str]] = []

    async def handler(event: SampleIntegrationEvent) -> None:
        seen.append(dict(current_rabbitmq_message_headers()))

    consumer.register(SampleIntegrationEvent, handler)
    broker = await start(consumer)

    await broker.deliver(
        "SampleIntegrationEvent", headers={"text": "a", "raw": b"b", "count": 3}
    )

    assert seen == [{"text": "a", "raw": "b"}]
    assert current_rabbitmq_message_headers() == {}


@pytest.mark.asyncio
async def test_async_handler_failure_exhausted_expect_other_handler_runs_and_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한 핸들러가 실패해도 나머지는 실행되고, 소진된 메시지는 메타데이터와 함께 dlq로 간다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    failing = AsyncMock(side_effect=RuntimeError("boom"))
    healthy = AsyncMock()
    consumer.register(
        SampleIntegrationEvent, failing, subscriber="billing", handler_name="failing"
    )
    consumer.register(
        SampleIntegrationEvent, healthy, subscriber="billing", handler_name="healthy"
    )
    broker = await start(consumer)

    message = await broker.deliver(
        "SampleIntegrationEvent.billing", headers={"traceparent": "t"}
    )

    healthy.assert_awaited_once()
    queue, copy = broker.published()
    assert queue == "SampleIntegrationEvent.billing.dlq"
    assert copy.body == BODY
    assert copy.delivery_mode is DeliveryMode.PERSISTENT
    assert copy.expiration is None
    assert copy.headers["traceparent"] == "t"
    dead_letter = DeadLetter.from_headers(
        AsyncRabbitMQEventConsumer._to_string_headers(copy.headers)
    )
    assert dead_letter.event_name == "SampleIntegrationEvent"
    assert dead_letter.subscriber == "billing"
    assert dead_letter.attempts == 1
    assert dead_letter.failures == (
        HandlerFailure(
            handler="failing",
            exception_type="RuntimeError",
            exception_message="boom",
            retryable=True,
        ),
    )
    message.ack.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_dead_letter_not_confirmed_expect_original_requeued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """브로커가 dlq 사본을 확인하지 않으면 원본을 ack하지 않고 되돌린다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, AsyncMock(side_effect=RuntimeError("x")))
    broker = await start(consumer)
    broker.publish_channel.default_exchange.publish.side_effect = DeliveryError(
        None, MagicMock()
    )

    message = await broker.deliver("SampleIntegrationEvent")

    message.ack.assert_not_called()
    message.nack.assert_awaited_once_with(requeue=True)


@pytest.mark.asyncio
async def test_async_malformed_payload_expect_dead_letter_without_handler_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """역직렬화할 수 없는 payload는 재시도 없이 모든 핸들러를 실패로 기록해 dlq로 보낸다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MAX_ATTEMPTS="5")
    )
    handler = AsyncMock()
    consumer.register(SampleIntegrationEvent, handler, handler_name="only")
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent", body=b"not json")

    handler.assert_not_called()
    queue, copy = broker.published()
    assert queue == "SampleIntegrationEvent.dlq"
    assert copy.body == b"not json"
    dead_letter = DeadLetter.from_headers(
        AsyncRabbitMQEventConsumer._to_string_headers(copy.headers)
    )
    assert dead_letter.subscriber is None
    assert dead_letter.attempts == 1
    assert [failure.handler for failure in dead_letter.failures] == ["only"]
    assert dead_letter.failures[0].exception_type == "ValidationError"
    assert dead_letter.failures[0].retryable is False
    message.ack.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_invalid_delivery_headers_expect_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재시도 상태 헤더를 읽을 수 없는 메시지는 처리하지 않고 dlq로 보낸다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    handler = AsyncMock()
    consumer.register(SampleIntegrationEvent, handler)
    broker = await start(consumer)

    await broker.deliver(
        "SampleIntegrationEvent", headers={DeliveryHeader.ATTEMPT.value: "many"}
    )

    handler.assert_not_called()
    queue, copy = broker.published()
    assert queue == "SampleIntegrationEvent.dlq"
    dead_letter = DeadLetter.from_headers(
        AsyncRabbitMQEventConsumer._to_string_headers(copy.headers)
    )
    assert dead_letter.failures[0].exception_type == "InvalidDeliveryHeaderError"
    assert dead_letter.failures[0].retryable is False


@pytest.mark.asyncio
async def test_async_non_retryable_failure_expect_dead_letter_on_first_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재시도해도 고칠 수 없는 실패는 남은 시도를 건너뛰고 dlq로 간다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MAX_ATTEMPTS="3")
    )
    handler = AsyncMock(side_effect=PermanentFailureError())
    consumer.register(SampleIntegrationEvent, handler)
    broker = await start(consumer)

    await broker.deliver("SampleIntegrationEvent")

    handler.assert_awaited_once()
    _, copy = broker.published()
    dead_letter = DeadLetter.from_headers(
        AsyncRabbitMQEventConsumer._to_string_headers(copy.headers)
    )
    assert dead_letter.attempts == 1
    assert dead_letter.failures[0].retryable is False


@pytest.mark.asyncio
async def test_async_blocking_retry_expect_only_failed_handler_reruns_before_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BLOCKING 재시도는 ack 없이 기다렸다가 실패한 핸들러만 다음 시도로 다시 실행한다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MAX_ATTEMPTS="2")
    )
    attempts: list[int] = []

    async def flaky(event: SampleIntegrationEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise RuntimeError("not yet")

    steady = AsyncMock()
    consumer.register(SampleIntegrationEvent, flaky, handler_name="flaky")
    consumer.register(SampleIntegrationEvent, steady, handler_name="steady")
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    assert attempts == [1, 2]
    steady.assert_awaited_once()
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_called()
    broker.publish_channel.default_exchange.publish.assert_not_called()


@pytest.mark.asyncio
async def test_async_blocking_retry_stopped_while_waiting_expect_message_requeued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대기 중 서비스가 멈추면 다시 실행하지 않고 메시지를 브로커에 되돌린다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MAX_ATTEMPTS="2", RETRY__INITIAL_INTERVAL="30")
    )
    stop_event = Event()

    async def failing(event: SampleIntegrationEvent) -> None:
        stop_event.set()
        raise RuntimeError("not yet")

    handler = AsyncMock(side_effect=failing)
    consumer.register(SampleIntegrationEvent, handler)
    broker = Broker()
    consumer.set_stop_event(stop_event)
    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        await consumer.initialize_async()

    message = await broker.deliver("SampleIntegrationEvent")

    handler.assert_awaited_once()
    message.ack.assert_not_called()
    message.nack.assert_awaited_once_with(requeue=True)


@pytest.mark.asyncio
async def test_async_deferred_handler_expect_wait_without_counting_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EventDeferredError는 기다린 뒤 다시 전달하되 시도 횟수를 늘리지 않는다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    attempts: list[int] = []

    async def deferring(event: SampleIntegrationEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise EventDeferredError(retry_after=0.001)

    consumer.register(SampleIntegrationEvent, deferring)
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    assert attempts == [1, 1]
    message.ack.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_delayed_retry_expect_copy_with_state_in_wait_queue_then_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELAYED 재시도는 상태 헤더와 만료 시간을 실은 사본을 대기 큐에 넣고 원본을 ack한다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(
            monkeypatch,
            RETRY__MODE="delayed",
            RETRY__MAX_ATTEMPTS="3",
            RETRY__INITIAL_INTERVAL="1.5",
        )
    )
    flaky = AsyncMock(side_effect=RuntimeError("not yet"))
    consumer.register(
        SampleIntegrationEvent, flaky, subscriber="billing", handler_name="flaky"
    )
    consumer.register(
        SampleIntegrationEvent, AsyncMock(), subscriber="billing", handler_name="ok"
    )
    broker = await start(consumer)

    message = await broker.deliver(
        "SampleIntegrationEvent.billing", headers={"traceparent": "t"}
    )

    flaky.assert_awaited_once()
    queue, copy = broker.published()
    assert queue == "SampleIntegrationEvent.billing.retry"
    assert copy.body == BODY
    assert copy.expiration == timedelta(seconds=1.5)
    assert copy.delivery_mode is DeliveryMode.PERSISTENT
    assert copy.headers["traceparent"] == "t"
    assert DeliveryState.from_headers(
        AsyncRabbitMQEventConsumer._to_string_headers(copy.headers)
    ) == DeliveryState(attempt=2, pending=frozenset({"flaky"}))
    message.ack.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_retry_copy_exhausted_expect_only_pending_handler_runs_and_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대기 큐에서 돌아온 사본은 남은 핸들러만 실행하고, 소진되면 누적 시도 횟수로 dlq에 간다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MODE="delayed", RETRY__MAX_ATTEMPTS="2")
    )
    flaky = AsyncMock(side_effect=RuntimeError("still down"))
    done = AsyncMock()
    consumer.register(SampleIntegrationEvent, flaky, handler_name="flaky")
    consumer.register(SampleIntegrationEvent, done, handler_name="done")
    broker = await start(consumer)

    await broker.deliver(
        "SampleIntegrationEvent",
        headers=dict(
            DeliveryState(attempt=2, pending=frozenset({"flaky"})).to_headers()
        ),
    )

    done.assert_not_called()
    queue, copy = broker.published()
    assert queue == "SampleIntegrationEvent.dlq"
    assert copy.headers[DeadLetterHeader.ATTEMPTS.value] == "2"
    assert DeadLetter.from_headers(
        AsyncRabbitMQEventConsumer._to_string_headers(copy.headers)
    ).pending == frozenset({"flaky"})


@pytest.mark.asyncio
async def test_async_auth_challenge_default_expect_handler_skipped_and_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHALLENGE 거부는 기본 정책에서 해당 핸들러만 건너뛰고 메시지를 ack한다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    denied = AsyncMock(
        side_effect=AuthRequirementDeniedError(
            AuthorizationDecision.challenge(AuthorizationReasonCode.SNAPSHOT_MISSING)
        )
    )
    other = AsyncMock()
    consumer.register(SampleIntegrationEvent, denied)
    consumer.register(SampleIntegrationEvent, other)
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    other.assert_awaited_once()
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_called()


@pytest.mark.asyncio
async def test_async_auth_deny_with_nack_drop_expect_message_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """nack_drop 정책의 DENY는 메시지를 requeue 없이 거부한다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, AUTH_DENY_ACTION="nack_drop")
    )
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(
            side_effect=AuthRequirementDeniedError(
                AuthorizationDecision.deny(AuthorizationReasonCode.POLICY_DENIED)
            )
        ),
    )
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    message.ack.assert_not_called()
    message.nack.assert_awaited_once_with(requeue=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision",
    [
        AuthorizationDecision.error(
            AuthorizationReasonCode.VERIFICATION_PROVIDER_UNAVAILABLE
        ),
        AuthorizationDecision.allow(),
        None,
    ],
    ids=["error", "allow", "missing"],
)
async def test_async_auth_error_default_expect_requeue_and_later_handlers_not_run(
    monkeypatch: pytest.MonkeyPatch, decision: AuthorizationDecision | None
) -> None:
    """ERROR로 취급되는 거부는 기본 정책에서 나머지 핸들러를 실행하지 않고 메시지를 되돌린다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    later = AsyncMock()
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(side_effect=AuthRequirementDeniedError(decision)),
    )
    consumer.register(SampleIntegrationEvent, later)
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    later.assert_not_called()
    message.ack.assert_not_called()
    message.nack.assert_awaited_once_with(requeue=True)
    broker.publish_channel.default_exchange.publish.assert_not_called()


@pytest.mark.asyncio
async def test_async_auth_provider_unavailable_expect_message_not_acknowledged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """인증 provider 장애는 메시지에 대한 판정이 아니므로 ack하지 않고 되돌린다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(side_effect=AuthVerificationProviderUnavailableError()),
    )
    broker = await start(consumer)

    message = await broker.deliver("SampleIntegrationEvent")

    message.ack.assert_not_called()
    message.nack.assert_awaited_once_with(requeue=True)


@pytest.mark.asyncio
async def test_async_message_with_traceparent_expect_child_context_then_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """traceparent 헤더가 있으면 child TraceContext로 실행하고 끝나면 지운다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.set_propagator(W3CTracePropagator())
    captured: list[TraceContext | None] = []

    async def handler(event: SampleIntegrationEvent) -> None:
        captured.append(TraceContext.get())

    consumer.register(SampleIntegrationEvent, handler)
    broker = await start(consumer)

    await broker.deliver(
        "SampleIntegrationEvent", headers={"traceparent": SAMPLE_TRACEPARENT}
    )

    context = captured[0]
    assert context is not None
    assert context.trace_id == SAMPLE_TRACE_ID
    assert context.parent_span_id == SAMPLE_SPAN_ID
    assert TraceContext.get() is None


@pytest.mark.asyncio
async def test_async_message_without_traceparent_expect_new_root_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """propagator가 있는데 trace 헤더가 없으면 새 루트 TraceContext로 실행한다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.set_propagator(W3CTracePropagator())
    captured: list[TraceContext | None] = []

    async def handler(event: SampleIntegrationEvent) -> None:
        captured.append(TraceContext.get())

    consumer.register(SampleIntegrationEvent, handler)
    broker = await start(consumer)

    await broker.deliver("SampleIntegrationEvent")

    context = captured[0]
    assert context is not None
    assert context.parent_span_id is None


@pytest.mark.asyncio
async def test_async_message_without_propagator_expect_no_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """propagator가 없으면 trace 헤더가 있어도 TraceContext를 만들지 않는다."""
    TraceContext.clear()
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    captured: list[TraceContext | None] = []

    async def handler(event: SampleIntegrationEvent) -> None:
        captured.append(TraceContext.get())

    consumer.register(SampleIntegrationEvent, handler)
    broker = await start(consumer)

    await broker.deliver(
        "SampleIntegrationEvent", headers={"traceparent": SAMPLE_TRACEPARENT}
    )

    assert captured == [None]


@pytest.mark.asyncio
async def test_async_run_expect_waiting_until_stop_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_async는 stop event가 설정되면 끝난다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    stop_event = Event()
    consumer.set_stop_event(stop_event)
    stop_event.set()

    await consumer.run_async()

    assert stop_event.is_set()


@pytest.mark.asyncio
async def test_async_dispose_expect_channel_and_connection_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dispose_async는 채널과 연결을 닫는다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    broker = await start(consumer)

    await consumer.dispose_async()

    broker.channel.close.assert_awaited_once_with()
    broker.connection.close.assert_awaited_once_with()


def dead_letter_message(*pending: str, body: bytes = BODY) -> AsyncMock:
    """Build what `queue.get` returns for one stored dead letter."""
    dead_letter = DeadLetter.model_validate(
        {
            "event_name": "SampleIntegrationEvent",
            "subscriber": "billing",
            "failures": [
                {
                    "handler": handler,
                    "exception_type": "RuntimeError",
                    "exception_message": "boom",
                    "retryable": True,
                }
                for handler in pending or ("flaky",)
            ],
            "attempts": 1,
            "failed_at": "2026-01-01T00:00:00+00:00",
        }
    )
    return incoming(body, dict(dead_letter.to_headers()))


class RedriveBroker:
    """Mocked dedicated connection a redrive opens."""

    connection: AsyncMock
    channel: AsyncMock
    publish_channel: AsyncMock
    queue: AsyncMock

    def __init__(self, *messages: AsyncMock | None) -> None:
        self.queue = AsyncMock()
        self.queue.get = AsyncMock(side_effect=list(messages))
        self.channel = AsyncMock()
        self.channel.declare_queue = AsyncMock(return_value=self.queue)
        self.publish_channel = AsyncMock()
        self.connection = AsyncMock()
        self.connection.channel = AsyncMock(
            side_effect=[self.channel, self.publish_channel]
        )
        self.connection.__aenter__ = AsyncMock(return_value=self.connection)
        self.connection.__aexit__ = AsyncMock(return_value=None)

    def published(self) -> tuple[str, Message, dict[str, str]]:
        """Return queue, message and headers of the single republished copy."""
        publish = self.publish_channel.default_exchange.publish
        assert publish.call_count == 1
        copy: Message = publish.call_args.args[0]
        return (
            publish.call_args.kwargs["routing_key"],
            copy,
            AsyncRabbitMQEventConsumer._to_string_headers(copy.headers),
        )


@pytest.mark.asyncio
async def test_async_redrive_success_expect_only_failed_handler_runs_and_dead_letter_acked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redrive는 실패로 기록된 핸들러만 실행하고 성공한 dead letter를 지운다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    flaky, done = AsyncMock(), AsyncMock()
    consumer.register(
        SampleIntegrationEvent, flaky, subscriber="billing", handler_name="flaky"
    )
    consumer.register(
        SampleIntegrationEvent, done, subscriber="billing", handler_name="done"
    )
    message = dead_letter_message()
    broker = RedriveBroker(message, None)

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=1, failed=0)
    flaky.assert_awaited_once()
    done.assert_not_called()
    assert broker.connection.channel.call_args_list[1].kwargs == {
        "on_return_raises": True
    }
    broker.channel.declare_queue.assert_awaited_once_with(
        "SampleIntegrationEvent.billing.dlq", durable=True
    )
    broker.queue.get.assert_awaited_with(fail=False)
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_called()
    broker.publish_channel.default_exchange.publish.assert_not_called()
    broker.connection.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_redrive_partly_failing_again_expect_metadata_narrowed_to_failed_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redrive에서 일부만 성공하면, 다시 실패한 핸들러만 남긴 사본으로 dead letter를 바꾼다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent, AsyncMock(), subscriber="billing", handler_name="fixed"
    )
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(side_effect=RuntimeError("still down")),
        subscriber="billing",
        handler_name="broken",
    )
    message = dead_letter_message("fixed", "broken")
    broker = RedriveBroker(message, None)

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=0, failed=1)
    queue, copy, headers = broker.published()
    assert queue == "SampleIntegrationEvent.billing.dlq"
    assert copy.body == BODY
    assert copy.expiration is None
    narrowed = DeadLetter.from_headers(headers)
    assert narrowed.pending == frozenset({"broken"})
    assert narrowed.failures[0].exception_message == "still down"
    assert narrowed.subscriber == "billing"
    # 사본이 확인된 뒤 예전 dead letter를 지운다.
    message.ack.assert_awaited_once_with()
    message.nack.assert_not_called()


@pytest.mark.asyncio
async def test_async_redrive_failing_again_expect_copy_published_only_after_the_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """다시 실패한 dead letter의 사본은 남은 것을 모두 꺼낸 뒤에 넣어, 한 호출에서 한 번만 전달된다."""
    consumer = AsyncRabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MAX_ATTEMPTS="3")
    )
    flaky = AsyncMock(side_effect=[RuntimeError("still down"), None])
    consumer.register(
        SampleIntegrationEvent, flaky, subscriber="billing", handler_name="flaky"
    )
    failing, recovering = dead_letter_message(), dead_letter_message()
    stored = iter([failing, recovering, None])
    broker = RedriveBroker()
    published_before_drained: list[int] = []

    async def take(*, fail: bool) -> AsyncMock | None:
        published_before_drained.append(
            broker.publish_channel.default_exchange.publish.call_count
        )
        return next(stored)

    broker.queue.get = AsyncMock(side_effect=take)

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=1, failed=1)
    assert published_before_drained == [0, 0, 0]
    _, _, headers = broker.published()
    assert DeadLetter.from_headers(headers).failures[0].exception_message == (
        "still down"
    )
    recovering.ack.assert_awaited_once_with()
    failing.ack.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_redrive_deferred_again_expect_original_failure_kept_for_deferred_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redrive 중 미뤄진 핸들러는 원래 실패 기록 그대로 남고, 성공한 핸들러는 빠진다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent, AsyncMock(), subscriber="billing", handler_name="fixed"
    )
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(side_effect=EventDeferredError(retry_after=5.0)),
        subscriber="billing",
        handler_name="waiting",
    )
    broker = RedriveBroker(dead_letter_message("fixed", "waiting"), None)

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=0, failed=1)
    _, _, headers = broker.published()
    assert DeadLetter.from_headers(headers).failures == (
        HandlerFailure(
            handler="waiting",
            exception_type="RuntimeError",
            exception_message="boom",
            retryable=True,
        ),
    )


@pytest.mark.asyncio
async def test_async_redrive_malformed_payload_expect_only_pending_handlers_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """역직렬화할 수 없는 dead letter는 실패로 기록돼 있던 핸들러만 계속 실패로 남긴다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    flaky, done = AsyncMock(), AsyncMock()
    consumer.register(
        SampleIntegrationEvent, flaky, subscriber="billing", handler_name="flaky"
    )
    consumer.register(
        SampleIntegrationEvent, done, subscriber="billing", handler_name="done"
    )
    broker = RedriveBroker(dead_letter_message("flaky", body=b"not json"), None)

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=0, failed=1)
    flaky.assert_not_called()
    done.assert_not_called()
    _, copy, headers = broker.published()
    assert copy.body == b"not json"
    narrowed = DeadLetter.from_headers(headers)
    assert narrowed.pending == frozenset({"flaky"})
    assert narrowed.failures[0].exception_type == "ValidationError"


@pytest.mark.asyncio
async def test_async_redrive_copy_not_confirmed_expect_old_dead_letter_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """갱신한 사본을 브로커가 확인하지 않으면 예전 dead letter를 지우지 않고 되돌린다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(side_effect=RuntimeError("still down")),
        subscriber="billing",
        handler_name="flaky",
    )
    message = dead_letter_message()
    broker = RedriveBroker(message, None)
    broker.publish_channel.default_exchange.publish.side_effect = DeliveryError(
        None, MagicMock()
    )

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=0, failed=1)
    message.ack.assert_not_called()
    message.nack.assert_awaited_once_with(requeue=True)


@pytest.mark.asyncio
async def test_async_redrive_with_limit_expect_no_more_dead_letters_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """limit만큼만 dead letter를 꺼낸다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent, AsyncMock(), subscriber="billing", handler_name="flaky"
    )
    broker = RedriveBroker(dead_letter_message(), dead_letter_message())

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(
            SampleIntegrationEvent, subscriber="billing", limit=1
        )

    assert result == RedriveResult(succeeded=1, failed=0)
    assert broker.queue.get.await_count == 1


@pytest.mark.asyncio
async def test_async_redrive_without_metadata_expect_message_kept_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dead-letter 메타데이터가 없는 메시지는 핸들러를 실행하지 않고 그대로 dlq에 남긴다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    handler = AsyncMock()
    consumer.register(SampleIntegrationEvent, handler, subscriber="billing")
    broker = RedriveBroker(incoming(headers={"origin": "manual"}), None)

    with patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection):
        result = await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=0, failed=1)
    handler.assert_not_called()
    queue, copy, headers = broker.published()
    assert queue == "SampleIntegrationEvent.billing.dlq"
    assert copy.body == BODY
    assert headers == {"origin": "manual"}


@pytest.mark.asyncio
async def test_async_redrive_unknown_subscription_expect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """등록되지 않은 구독자의 redrive는 SubscriptionNotFoundError로 실패한다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, AsyncMock(), subscriber="billing")

    with pytest.raises(SubscriptionNotFoundError):
        await consumer.redrive(SampleIntegrationEvent, subscriber="shipping")


@pytest.mark.asyncio
async def test_async_redrive_auth_provider_unavailable_expect_error_and_nothing_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redrive 중 인증 provider 장애는 그대로 전파되고, 꺼낸 메시지는 확인하지 않은 채 연결을 닫아 dlq에 남긴다."""
    consumer = AsyncRabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent,
        AsyncMock(
            side_effect=[
                RuntimeError("still down"),
                AuthVerificationProviderUnavailableError(),
            ]
        ),
        subscriber="billing",
        handler_name="flaky",
    )
    held, interrupted = dead_letter_message(), dead_letter_message()
    broker = RedriveBroker(held, interrupted)

    with (
        patch(CONNECT, new_callable=AsyncMock, return_value=broker.connection),
        pytest.raises(AuthVerificationProviderUnavailableError),
    ):
        await consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    held.ack.assert_not_called()
    interrupted.ack.assert_not_called()
    broker.publish_channel.default_exchange.publish.assert_not_called()
    broker.connection.__aexit__.assert_awaited_once()
