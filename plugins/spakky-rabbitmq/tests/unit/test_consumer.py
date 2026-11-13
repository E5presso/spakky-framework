"""Unit tests for the synchronous RabbitMQ consumer.

The broker is replaced by mocks; every test drives the consumer through the
callback it registers with `basic_consume`, exactly as pika would.
"""

from collections.abc import Callable
from threading import Event
from typing import override
from unittest.mock import MagicMock, patch

import pytest
from pika.exceptions import NackError, UnroutableError
from pika.spec import BasicProperties
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
from spakky.plugins.rabbitmq.event.consumer import RabbitMQEventConsumer

CONNECTION = "spakky.plugins.rabbitmq.event.consumer.BlockingConnection"
BODY = b'{"data": "test"}'
SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"

type MessageCallback = Callable[[MagicMock, MagicMock, BasicProperties, bytes], None]


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
    """Mocked connection and channels a started consumer talks to."""

    connection: MagicMock
    channel: MagicMock
    publish_channel: MagicMock

    def __init__(self) -> None:
        self.connection = MagicMock()
        self.channel = MagicMock()
        self.publish_channel = MagicMock()
        self.connection.channel.side_effect = [self.channel, self.publish_channel]

    def callback(self, queue: str) -> MessageCallback:
        """Return the callback the consumer registered for a queue."""
        for call in self.channel.basic_consume.call_args_list:
            if call.args[0] == queue:
                return call.args[1]
        raise LookupError(queue)

    def deliver(
        self,
        queue: str,
        *,
        body: bytes = BODY,
        headers: dict[str, object] | None = None,
        delivery_tag: int = 7,
    ) -> None:
        """Hand one message to the consumer as pika would."""
        method_frame = MagicMock()
        method_frame.consumer_tag = "ctag"
        method_frame.delivery_tag = delivery_tag
        self.callback(queue)(
            self.channel, method_frame, BasicProperties(headers=headers), body
        )

    def published(self) -> tuple[str, bytes, BasicProperties, dict[str, str]]:
        """Return queue, body, properties and headers of the single forwarded copy."""
        call = self.publish_channel.basic_publish.call_args
        assert self.publish_channel.basic_publish.call_count == 1
        assert call.args[0] == ""
        assert call.kwargs["mandatory"] is True
        properties: BasicProperties = call.kwargs["properties"]
        return (
            call.args[1],
            call.args[2],
            properties,
            RabbitMQEventConsumer._to_string_headers(properties.headers),
        )


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


def start(consumer: RabbitMQEventConsumer) -> Broker:
    """Initialize the consumer against a mocked broker."""
    broker = Broker()
    consumer.set_stop_event(Event())
    with patch(CONNECTION, return_value=broker.connection):
        consumer.initialize()
    return broker


def test_sync_initialize_unnamed_blocking_expect_event_queue_bound_with_prefetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이름 없는 구독자는 이벤트 이름 큐를 쓰고 BLOCKING 모드에서 prefetch 1을 건다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, MagicMock())

    broker = start(consumer)

    broker.publish_channel.confirm_delivery.assert_called_once_with()
    broker.channel.basic_qos.assert_called_once_with(prefetch_count=1)
    broker.channel.exchange_declare.assert_called_once_with("test_exchange")
    assert [call.args[0] for call in broker.channel.queue_declare.call_args_list] == [
        "SampleIntegrationEvent",
        "SampleIntegrationEvent.dlq",
    ]
    broker.channel.queue_bind.assert_called_once_with(
        "SampleIntegrationEvent", "test_exchange", "SampleIntegrationEvent"
    )
    assert broker.channel.basic_consume.call_args.args[0] == "SampleIntegrationEvent"


def test_sync_initialize_named_delayed_expect_own_queue_and_wait_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이름 있는 구독자는 자신의 큐·dlq·대기 큐를 갖고 대기 큐는 자기 큐로만 되돌린다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, RETRY__MODE="delayed"))
    consumer.register(RenamedIntegrationEvent, MagicMock(), subscriber="billing")

    broker = start(consumer)

    broker.channel.basic_qos.assert_not_called()
    declared = {
        call.args[0]: call.kwargs
        for call in broker.channel.queue_declare.call_args_list
    }
    assert declared == {
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
    broker.channel.queue_bind.assert_called_once_with(
        "external.renamed.v1.billing", "test_exchange", "external.renamed.v1"
    )


def test_sync_initialize_without_exchange_expect_no_exchange_or_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """exchange가 없으면 기본 exchange에 맡기고 선언·바인딩을 하지 않는다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, exchange=None))
    consumer.register(SampleIntegrationEvent, MagicMock())

    broker = start(consumer)

    broker.channel.exchange_declare.assert_not_called()
    broker.channel.queue_bind.assert_not_called()
    assert broker.channel.basic_consume.call_count == 1


def test_sync_register_named_subscriber_without_exchange_expect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """exchange 없이 이름 있는 구독자를 등록하면 전용 에러로 실패한다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, exchange=None))

    with pytest.raises(SubscriberExchangeRequiredError) as raised:
        consumer.register(SampleIntegrationEvent, MagicMock(), subscriber="billing")

    assert raised.value.subscriber == "billing"
    assert raised.value.event_type is SampleIntegrationEvent


@pytest.mark.parametrize(("consumer_tag", "delivery_tag"), [(None, 1), ("ctag", None)])
def test_sync_message_without_tags_expect_invalid_message_error(
    monkeypatch: pytest.MonkeyPatch,
    consumer_tag: str | None,
    delivery_tag: int | None,
) -> None:
    """consumer tag나 delivery tag가 없는 메시지는 InvalidMessageError로 거부한다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, MagicMock())
    broker = start(consumer)
    method_frame = MagicMock()
    method_frame.consumer_tag = consumer_tag
    method_frame.delivery_tag = delivery_tag

    with pytest.raises(InvalidMessageError):
        broker.callback("SampleIntegrationEvent")(
            broker.channel, method_frame, BasicProperties(), BODY
        )


def test_sync_message_all_handlers_succeed_expect_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """모든 핸들러가 성공하면 메시지를 ack한다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    first, second = MagicMock(), MagicMock()
    consumer.register(SampleIntegrationEvent, first)
    consumer.register(SampleIntegrationEvent, second)
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    assert first.call_args.args[0].data == "test"
    second.assert_called_once()
    broker.channel.basic_ack.assert_called_once_with(7)
    broker.publish_channel.basic_publish.assert_not_called()


def test_sync_message_headers_expect_decoded_strings_visible_to_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bytes 헤더는 문자열로 풀리고 문자열이 아닌 값은 빠진 채 핸들러에 보인다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    seen: list[dict[str, str]] = []
    consumer.register(
        SampleIntegrationEvent,
        lambda event: seen.append(dict(current_rabbitmq_message_headers())),
    )
    broker = start(consumer)

    broker.deliver(
        "SampleIntegrationEvent", headers={"text": "a", "raw": b"b", "count": 3}
    )

    assert seen == [{"text": "a", "raw": "b"}]
    assert current_rabbitmq_message_headers() == {}


def test_sync_handler_failure_exhausted_expect_other_handler_runs_and_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한 핸들러가 실패해도 나머지는 실행되고, 소진된 메시지는 메타데이터와 함께 dlq로 간다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    failing = MagicMock(side_effect=RuntimeError("boom"))
    healthy = MagicMock()
    consumer.register(
        SampleIntegrationEvent, failing, subscriber="billing", handler_name="failing"
    )
    consumer.register(
        SampleIntegrationEvent, healthy, subscriber="billing", handler_name="healthy"
    )
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent.billing", headers={"traceparent": "t"})

    healthy.assert_called_once()
    queue, body, properties, headers = broker.published()
    assert queue == "SampleIntegrationEvent.billing.dlq"
    assert body == BODY
    assert properties.delivery_mode == 2
    assert properties.expiration is None
    assert headers["traceparent"] == "t"
    dead_letter = DeadLetter.from_headers(headers)
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
    broker.channel.basic_ack.assert_called_once_with(7)


@pytest.mark.parametrize(
    "error", [UnroutableError([]), NackError([])], ids=["returned", "nacked"]
)
def test_sync_dead_letter_not_confirmed_expect_original_requeued(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """브로커가 dlq 사본을 확인하지 않으면 원본을 ack하지 않고 되돌린다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, MagicMock(side_effect=RuntimeError("x")))
    broker = start(consumer)
    broker.publish_channel.basic_publish.side_effect = error

    broker.deliver("SampleIntegrationEvent")

    broker.channel.basic_ack.assert_not_called()
    broker.channel.basic_nack.assert_called_once_with(7, requeue=True)


def test_sync_malformed_payload_expect_dead_letter_without_handler_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """역직렬화할 수 없는 payload는 재시도 없이 모든 핸들러를 실패로 기록해 dlq로 보낸다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, RETRY__MAX_ATTEMPTS="5"))
    handler = MagicMock()
    consumer.register(SampleIntegrationEvent, handler, handler_name="only")
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent", body=b"not json")

    handler.assert_not_called()
    queue, body, properties, headers = broker.published()
    assert queue == "SampleIntegrationEvent.dlq"
    assert body == b"not json"
    dead_letter = DeadLetter.from_headers(headers)
    assert dead_letter.subscriber is None
    assert dead_letter.attempts == 1
    assert [failure.handler for failure in dead_letter.failures] == ["only"]
    assert dead_letter.failures[0].exception_type == "ValidationError"
    assert dead_letter.failures[0].retryable is False
    broker.channel.basic_ack.assert_called_once_with(7)


def test_sync_invalid_delivery_headers_expect_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재시도 상태 헤더를 읽을 수 없는 메시지는 처리하지 않고 dlq로 보낸다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    handler = MagicMock()
    consumer.register(SampleIntegrationEvent, handler)
    broker = start(consumer)

    broker.deliver(
        "SampleIntegrationEvent", headers={DeliveryHeader.ATTEMPT.value: "many"}
    )

    handler.assert_not_called()
    queue, _, _, headers = broker.published()
    assert queue == "SampleIntegrationEvent.dlq"
    dead_letter = DeadLetter.from_headers(headers)
    assert dead_letter.failures[0].exception_type == "InvalidDeliveryHeaderError"
    assert dead_letter.failures[0].retryable is False


def test_sync_non_retryable_failure_expect_dead_letter_on_first_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """재시도해도 고칠 수 없는 실패는 남은 시도를 건너뛰고 dlq로 간다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, RETRY__MAX_ATTEMPTS="3"))
    consumer.register(
        SampleIntegrationEvent, MagicMock(side_effect=PermanentFailureError())
    )
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    broker.connection.call_later.assert_not_called()
    _, _, _, headers = broker.published()
    dead_letter = DeadLetter.from_headers(headers)
    assert dead_letter.attempts == 1
    assert dead_letter.failures[0].retryable is False


def test_sync_blocking_retry_expect_unacked_wait_then_only_failed_handler_reruns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BLOCKING 재시도는 ack 없이 기다렸다가 실패한 핸들러만 다음 시도로 다시 실행한다."""
    consumer = RabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MAX_ATTEMPTS="2", RETRY__INITIAL_INTERVAL="3")
    )
    attempts: list[int] = []

    def flaky(event: SampleIntegrationEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise RuntimeError("not yet")

    steady = MagicMock()
    consumer.register(SampleIntegrationEvent, flaky, handler_name="flaky")
    consumer.register(SampleIntegrationEvent, steady, handler_name="steady")
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    broker.channel.basic_ack.assert_not_called()
    broker.channel.basic_nack.assert_not_called()
    delay, redeliver = broker.connection.call_later.call_args.args
    assert delay == 3.0
    redeliver()
    assert attempts == [1, 2]
    steady.assert_called_once()
    broker.channel.basic_ack.assert_called_once_with(7)
    broker.publish_channel.basic_publish.assert_not_called()


def test_sync_blocking_retry_stopped_before_wait_ends_expect_message_left_unacked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대기 중 서비스가 멈추면 다시 실행하지 않고 메시지를 미확인 상태로 둔다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, RETRY__MAX_ATTEMPTS="2"))
    handler = MagicMock(side_effect=RuntimeError("not yet"))
    consumer.register(SampleIntegrationEvent, handler)
    stop_event = Event()
    broker = Broker()
    consumer.set_stop_event(stop_event)
    with patch(CONNECTION, return_value=broker.connection):
        consumer.initialize()
    broker.deliver("SampleIntegrationEvent")
    stop_event.set()

    broker.connection.call_later.call_args.args[1]()

    handler.assert_called_once()
    broker.channel.basic_ack.assert_not_called()
    broker.channel.basic_nack.assert_not_called()


def test_sync_deferred_handler_expect_wait_without_counting_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EventDeferredError는 요청한 시간만큼 기다리고 시도 횟수를 늘리지 않는다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    attempts: list[int] = []

    def deferring(event: SampleIntegrationEvent) -> None:
        attempts.append(EventDeliveryContext.current().attempt)
        if len(attempts) == 1:
            raise EventDeferredError(retry_after=7.0)

    consumer.register(SampleIntegrationEvent, deferring)
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    delay, redeliver = broker.connection.call_later.call_args.args
    assert delay == 7.0
    redeliver()
    assert attempts == [1, 1]
    broker.channel.basic_ack.assert_called_once_with(7)


def test_sync_delayed_retry_expect_copy_with_state_in_wait_queue_then_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELAYED 재시도는 상태 헤더와 만료 시간을 실은 사본을 대기 큐에 넣고 원본을 ack한다."""
    consumer = RabbitMQEventConsumer(
        make_config(
            monkeypatch,
            RETRY__MODE="delayed",
            RETRY__MAX_ATTEMPTS="3",
            RETRY__INITIAL_INTERVAL="1.5",
        )
    )
    consumer.register(
        SampleIntegrationEvent,
        MagicMock(side_effect=RuntimeError("not yet")),
        subscriber="billing",
        handler_name="flaky",
    )
    consumer.register(
        SampleIntegrationEvent, MagicMock(), subscriber="billing", handler_name="ok"
    )
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent.billing", headers={"traceparent": "t"})

    queue, body, properties, headers = broker.published()
    assert queue == "SampleIntegrationEvent.billing.retry"
    assert body == BODY
    assert properties.expiration == "1500"
    assert properties.delivery_mode == 2
    assert headers["traceparent"] == "t"
    assert DeliveryState.from_headers(headers) == DeliveryState(
        attempt=2, pending=frozenset({"flaky"})
    )
    broker.connection.call_later.assert_not_called()
    broker.channel.basic_ack.assert_called_once_with(7)


def test_sync_retry_copy_exhausted_expect_only_pending_handler_runs_and_dead_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """대기 큐에서 돌아온 사본은 남은 핸들러만 실행하고, 소진되면 누적 시도 횟수로 dlq에 간다."""
    consumer = RabbitMQEventConsumer(
        make_config(monkeypatch, RETRY__MODE="delayed", RETRY__MAX_ATTEMPTS="2")
    )
    flaky = MagicMock(side_effect=RuntimeError("still down"))
    done = MagicMock()
    consumer.register(SampleIntegrationEvent, flaky, handler_name="flaky")
    consumer.register(SampleIntegrationEvent, done, handler_name="done")
    broker = start(consumer)

    broker.deliver(
        "SampleIntegrationEvent",
        headers=dict(
            DeliveryState(attempt=2, pending=frozenset({"flaky"})).to_headers()
        ),
    )

    done.assert_not_called()
    queue, _, _, headers = broker.published()
    assert queue == "SampleIntegrationEvent.dlq"
    assert headers[DeadLetterHeader.ATTEMPTS.value] == "2"
    assert DeadLetter.from_headers(headers).pending == frozenset({"flaky"})


def test_sync_auth_challenge_default_expect_handler_skipped_and_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHALLENGE 거부는 기본 정책에서 해당 핸들러만 건너뛰고 메시지를 ack한다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    denied = MagicMock(
        side_effect=AuthRequirementDeniedError(
            AuthorizationDecision.challenge(AuthorizationReasonCode.SNAPSHOT_MISSING)
        )
    )
    other = MagicMock()
    consumer.register(SampleIntegrationEvent, denied)
    consumer.register(SampleIntegrationEvent, other)
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    other.assert_called_once()
    broker.channel.basic_ack.assert_called_once_with(7)
    broker.channel.basic_nack.assert_not_called()


def test_sync_auth_deny_with_nack_drop_expect_message_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """nack_drop 정책의 DENY는 메시지를 requeue 없이 거부한다."""
    consumer = RabbitMQEventConsumer(
        make_config(monkeypatch, AUTH_DENY_ACTION="nack_drop")
    )
    consumer.register(
        SampleIntegrationEvent,
        MagicMock(
            side_effect=AuthRequirementDeniedError(
                AuthorizationDecision.deny(AuthorizationReasonCode.POLICY_DENIED)
            )
        ),
    )
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    broker.channel.basic_ack.assert_not_called()
    broker.channel.basic_nack.assert_called_once_with(7, requeue=False)


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
def test_sync_auth_error_default_expect_requeue_and_later_handlers_not_run(
    monkeypatch: pytest.MonkeyPatch, decision: AuthorizationDecision | None
) -> None:
    """ERROR로 취급되는 거부는 기본 정책에서 나머지 핸들러를 실행하지 않고 메시지를 되돌린다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    later = MagicMock()
    consumer.register(
        SampleIntegrationEvent,
        MagicMock(side_effect=AuthRequirementDeniedError(decision)),
    )
    consumer.register(SampleIntegrationEvent, later)
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    later.assert_not_called()
    broker.channel.basic_ack.assert_not_called()
    broker.channel.basic_nack.assert_called_once_with(7, requeue=True)
    broker.publish_channel.basic_publish.assert_not_called()


def test_sync_auth_provider_unavailable_expect_message_not_acknowledged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """인증 provider 장애는 메시지에 대한 판정이 아니므로 ack하지 않고 되돌린다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent,
        MagicMock(side_effect=AuthVerificationProviderUnavailableError()),
    )
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    broker.channel.basic_ack.assert_not_called()
    broker.channel.basic_nack.assert_called_once_with(7, requeue=True)


def test_sync_message_with_traceparent_expect_child_context_then_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """traceparent 헤더가 있으면 child TraceContext로 실행하고 끝나면 지운다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.set_propagator(W3CTracePropagator())
    captured: list[TraceContext | None] = []
    consumer.register(
        SampleIntegrationEvent, lambda event: captured.append(TraceContext.get())
    )
    broker = start(consumer)

    broker.deliver(
        "SampleIntegrationEvent", headers={"traceparent": SAMPLE_TRACEPARENT}
    )

    context = captured[0]
    assert context is not None
    assert context.trace_id == SAMPLE_TRACE_ID
    assert context.parent_span_id == SAMPLE_SPAN_ID
    assert TraceContext.get() is None


def test_sync_message_without_traceparent_expect_new_root_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """propagator가 있는데 trace 헤더가 없으면 새 루트 TraceContext로 실행한다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.set_propagator(W3CTracePropagator())
    captured: list[TraceContext | None] = []
    consumer.register(
        SampleIntegrationEvent, lambda event: captured.append(TraceContext.get())
    )
    broker = start(consumer)

    broker.deliver("SampleIntegrationEvent")

    context = captured[0]
    assert context is not None
    assert context.parent_span_id is None


def test_sync_message_without_propagator_expect_no_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """propagator가 없으면 trace 헤더가 있어도 TraceContext를 만들지 않는다."""
    TraceContext.clear()
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    captured: list[TraceContext | None] = []
    consumer.register(
        SampleIntegrationEvent, lambda event: captured.append(TraceContext.get())
    )
    broker = start(consumer)

    broker.deliver(
        "SampleIntegrationEvent", headers={"traceparent": SAMPLE_TRACEPARENT}
    )

    assert captured == [None]


def test_sync_run_expect_consuming_until_stop_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run은 소비를 시작하고, stop event가 설정된 뒤에만 소비를 멈춘다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    stop_event = Event()
    broker = Broker()
    consumer.set_stop_event(stop_event)
    with patch(CONNECTION, return_value=broker.connection):
        consumer.initialize()

    consumer.run()
    check = broker.connection.add_callback_threadsafe.call_args.args[0]
    check()
    broker.channel.stop_consuming.assert_not_called()
    stop_event.set()
    check()

    broker.channel.start_consuming.assert_called_once_with()
    broker.channel.stop_consuming.assert_called_once_with()


def test_sync_dispose_expect_channel_and_connection_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dispose는 채널과 연결을 닫는다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    broker = start(consumer)

    consumer.dispose()

    broker.channel.close.assert_called_once_with()
    broker.connection.close.assert_called_once_with()


def dead_letter_message(
    delivery_tag: int, pending: str = "flaky"
) -> tuple[MagicMock, BasicProperties, bytes]:
    """Build what `basic_get` returns for one stored dead letter."""
    method_frame = MagicMock()
    method_frame.delivery_tag = delivery_tag
    dead_letter = DeadLetter.model_validate(
        {
            "event_name": "SampleIntegrationEvent",
            "subscriber": "billing",
            "failures": [
                {
                    "handler": pending,
                    "exception_type": "RuntimeError",
                    "exception_message": "boom",
                    "retryable": True,
                }
            ],
            "attempts": 1,
            "failed_at": "2026-01-01T00:00:00+00:00",
        }
    )
    return method_frame, BasicProperties(headers=dead_letter.to_headers()), BODY


def redrive_broker(*messages: tuple[MagicMock | None, object, object]) -> Broker:
    """Mock the dedicated connection a redrive opens."""
    broker = Broker()
    broker.connection.channel.side_effect = None
    broker.connection.channel.return_value = broker.channel
    broker.channel.basic_get.side_effect = list(messages)
    return broker


def test_sync_redrive_success_expect_only_failed_handler_runs_and_dead_letter_acked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redrive는 실패로 기록된 핸들러만 실행하고 성공한 dead letter를 지운다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    flaky, done = MagicMock(), MagicMock()
    consumer.register(
        SampleIntegrationEvent, flaky, subscriber="billing", handler_name="flaky"
    )
    consumer.register(
        SampleIntegrationEvent, done, subscriber="billing", handler_name="done"
    )
    broker = redrive_broker(dead_letter_message(11), (None, None, None))

    with patch(CONNECTION, return_value=broker.connection):
        result = consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=1, failed=0)
    flaky.assert_called_once()
    done.assert_not_called()
    broker.channel.queue_declare.assert_called_once_with(
        "SampleIntegrationEvent.billing.dlq", durable=True
    )
    broker.channel.basic_get.assert_called_with("SampleIntegrationEvent.billing.dlq")
    broker.channel.basic_ack.assert_called_once_with(11)
    broker.channel.basic_nack.assert_not_called()
    broker.connection.close.assert_called_once_with()


def test_sync_redrive_failing_again_expect_dead_letter_returned_after_the_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """다시 실패한 dead letter는 호출이 끝날 때 dlq로 되돌려 한 번만 전달된다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch, RETRY__MAX_ATTEMPTS="3"))
    flaky = MagicMock(side_effect=[RuntimeError("still down"), None])
    consumer.register(
        SampleIntegrationEvent, flaky, subscriber="billing", handler_name="flaky"
    )
    broker = redrive_broker(
        dead_letter_message(11), dead_letter_message(12), (None, None, None)
    )
    acked_before_return: list[int] = []
    broker.channel.basic_ack.side_effect = lambda tag: acked_before_return.append(
        broker.channel.basic_nack.call_count
    )

    with patch(CONNECTION, return_value=broker.connection):
        result = consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=1, failed=1)
    broker.channel.basic_ack.assert_called_once_with(12)
    broker.channel.basic_nack.assert_called_once_with(11, requeue=True)
    # 실패한 메시지는 뒤의 메시지를 모두 처리한 뒤에야 되돌린다.
    assert acked_before_return == [0]


def test_sync_redrive_with_limit_expect_no_more_dead_letters_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """limit만큼만 dead letter를 꺼낸다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent, MagicMock(), subscriber="billing", handler_name="flaky"
    )
    broker = redrive_broker(dead_letter_message(11), dead_letter_message(12))

    with patch(CONNECTION, return_value=broker.connection):
        result = consumer.redrive(SampleIntegrationEvent, subscriber="billing", limit=1)

    assert result == RedriveResult(succeeded=1, failed=0)
    assert broker.channel.basic_get.call_count == 1


def test_sync_redrive_without_metadata_expect_message_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dead-letter 메타데이터가 없는 메시지는 핸들러를 실행하지 않고 dlq에 남긴다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    handler = MagicMock()
    consumer.register(SampleIntegrationEvent, handler, subscriber="billing")
    method_frame = MagicMock()
    method_frame.delivery_tag = 11
    broker = redrive_broker(
        (method_frame, BasicProperties(headers={}), BODY), (None, None, None)
    )

    with patch(CONNECTION, return_value=broker.connection):
        result = consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    assert result == RedriveResult(succeeded=0, failed=1)
    handler.assert_not_called()
    broker.channel.basic_nack.assert_called_once_with(11, requeue=True)


def test_sync_redrive_unknown_subscription_expect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """등록되지 않은 구독자의 redrive는 SubscriptionNotFoundError로 실패한다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(SampleIntegrationEvent, MagicMock(), subscriber="billing")

    with pytest.raises(SubscriptionNotFoundError):
        consumer.redrive(SampleIntegrationEvent, subscriber="shipping")


def test_sync_redrive_auth_provider_unavailable_expect_error_and_connection_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """redrive 중 인증 provider 장애는 그대로 전파되고, 연결을 닫아 메시지를 dlq에 남긴다."""
    consumer = RabbitMQEventConsumer(make_config(monkeypatch))
    consumer.register(
        SampleIntegrationEvent,
        MagicMock(side_effect=AuthVerificationProviderUnavailableError()),
        subscriber="billing",
        handler_name="flaky",
    )
    broker = redrive_broker(dead_letter_message(11))

    with (
        patch(CONNECTION, return_value=broker.connection),
        pytest.raises(AuthVerificationProviderUnavailableError),
    ):
        consumer.redrive(SampleIntegrationEvent, subscriber="billing")

    broker.channel.basic_ack.assert_not_called()
    broker.connection.close.assert_called_once_with()
