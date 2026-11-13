"""Broker-neutral delivery contract shared by every integration consumer."""

from datetime import UTC, datetime

import pytest
from spakky.auth import (
    AuthContextNotFoundError,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
    AuthVerificationProviderUnavailableError,
)
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent

from spakky.event.delivery import (
    AsyncEventSubscriptions,
    AsyncSubscriptionDelivery,
    DeadLetter,
    DeadLetterHeader,
    DeliveryCompleted,
    DeliveryDeadLettered,
    DeliveryDeferred,
    DeliveryHeader,
    DeliveryRetry,
    DeliveryState,
    EventDeliveryContext,
    EventRouting,
    EventSubscriptions,
    HandlerFailure,
    RetryMode,
    RetryPolicy,
    SubscriptionDelivery,
)
from spakky.event.error import (
    AbstractNonRetryableEventError,
    EventDeferredError,
    EventDeliveryContextUnavailableError,
    InvalidDeliveryHeaderError,
    SubscriptionNotFoundError,
)
from spakky.event.subscription import (
    DuplicateEventHandlerNameError,
    InvalidSubscriberNameError,
    SubscriberNames,
)


@immutable
class OrderPlaced(AbstractIntegrationEvent):
    """An order was placed."""

    order: str


class PermanentFailure(AbstractNonRetryableEventError):
    """A failure no retry can fix."""

    message = "permanent"


class Recorder:
    """Collects handler calls and fails on demand."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.contexts: list[EventDeliveryContext] = []
        self.errors: dict[str, Exception] = {}

    def sync(self, name: str):
        def handle(event: OrderPlaced) -> None:
            self.calls.append(name)
            self.contexts.append(EventDeliveryContext.current())
            if name in self.errors:
                raise self.errors[name]

        return handle

    def asynchronous(self, name: str):
        async def handle(event: OrderPlaced) -> None:
            self.calls.append(name)
            self.contexts.append(EventDeliveryContext.current())
            if name in self.errors:
                raise self.errors[name]

        return handle


def sync_delivery(
    recorder: Recorder, policy: RetryPolicy, subscriber: str | None = "billing"
) -> SubscriptionDelivery:
    delivery = SubscriptionDelivery(OrderPlaced, subscriber, policy)
    delivery.add("first", recorder.sync("first"))
    delivery.add("second", recorder.sync("second"))
    return delivery


def async_delivery(
    recorder: Recorder, policy: RetryPolicy, subscriber: str | None = "billing"
) -> AsyncSubscriptionDelivery:
    delivery = AsyncSubscriptionDelivery(OrderPlaced, subscriber, policy)
    delivery.add("first", recorder.asynchronous("first"))
    delivery.add("second", recorder.asynchronous("second"))
    return delivery


def test_retry_policy_delay_expect_exponential_growth_capped_at_max() -> None:
    """재시도 간격은 배수로 늘고 상한에서 멈춘다."""
    policy = RetryPolicy(
        max_attempts=5, initial_interval=1.0, multiplier=3.0, max_interval=10.0
    )
    assert [policy.delay_after(attempt) for attempt in (1, 2, 3, 4)] == [
        1.0,
        3.0,
        9.0,
        10.0,
    ]
    assert RetryPolicy().delay_after(1) == 0.0
    assert RetryPolicy().mode is RetryMode.BLOCKING


def test_delivery_state_headers_expect_round_trip_and_first_delivery_default() -> None:
    """재시도 상태는 헤더로 오가고, 헤더가 없으면 첫 전달이다."""
    state = DeliveryState(attempt=3, pending=frozenset({"b", "a"}))
    assert DeliveryState.from_headers(state.to_headers()) == state
    assert DeliveryState.from_headers({}) == DeliveryState()
    assert DeliveryState().to_headers() == {DeliveryHeader.ATTEMPT.value: "1"}


@pytest.mark.parametrize(
    "headers",
    [
        {DeliveryHeader.ATTEMPT.value: "many"},
        {DeliveryHeader.ATTEMPT.value: "0"},
        {DeliveryHeader.PENDING_HANDLERS.value: "{not json"},
    ],
)
def test_delivery_state_malformed_headers_expect_rejected(
    headers: dict[str, str],
) -> None:
    """깨진 재시도 헤더는 조용히 첫 전달로 바뀌지 않는다."""
    with pytest.raises(InvalidDeliveryHeaderError):
        DeliveryState.from_headers(headers)


def test_dead_letter_headers_expect_round_trip_for_named_and_unnamed() -> None:
    """dead-letter 메타데이터는 헤더만으로 복원된다."""
    failure = HandlerFailure(
        handler="first",
        exception_type="RuntimeError",
        exception_message="boom",
        retryable=True,
    )
    for subscriber in ("billing", None):
        dead_letter = DeadLetter(
            event_name="OrderPlaced",
            subscriber=subscriber,
            failures=(failure,),
            attempts=3,
            failed_at=datetime(2026, 11, 14, tzinfo=UTC),
        )
        headers = dead_letter.to_headers()
        assert DeadLetter.from_headers(headers) == dead_letter
        assert dead_letter.pending == frozenset({"first"})
        assert headers[DeadLetterHeader.SUBSCRIBER.value] == (subscriber or "")


@pytest.mark.parametrize("broken", list(DeadLetterHeader))
def test_dead_letter_missing_or_malformed_header_expect_rejected(
    broken: DeadLetterHeader,
) -> None:
    """dead-letter 헤더가 빠지거나 깨지면 복원을 거부한다."""
    headers = DeadLetter(
        event_name="OrderPlaced",
        subscriber="billing",
        failures=(),
        attempts=1,
        failed_at=datetime(2026, 11, 14, tzinfo=UTC),
    ).to_headers()
    del headers[broken.value]
    with pytest.raises(InvalidDeliveryHeaderError):
        DeadLetter.from_headers(headers)
    with pytest.raises(InvalidDeliveryHeaderError):
        DeadLetter.from_headers(
            {**headers, DeadLetterHeader.ATTEMPTS.value: "many", broken.value: "x"}
        )


def test_sync_delivery_all_succeed_expect_completed_with_context_per_handler() -> None:
    """모든 처리기가 성공하면 완료이고, 처리기마다 전달 문맥이 잡힌다."""
    recorder = Recorder()
    event = OrderPlaced(order="o-1")
    outcome = sync_delivery(recorder, RetryPolicy(), subscriber=None).deliver(event)
    assert outcome == DeliveryCompleted()
    assert recorder.calls == ["first", "second"]
    assert [
        (c.subscriber, c.handler, c.event_id, c.attempt) for c in recorder.contexts
    ] == [
        ("", "first", event.event_id, 1),
        ("", "second", event.event_id, 1),
    ]
    assert EventDeliveryContext.current_or_none() is None
    with pytest.raises(EventDeliveryContextUnavailableError):
        EventDeliveryContext.current()


def test_sync_delivery_one_fails_expect_others_run_and_only_failed_retried() -> None:
    """한 처리기가 실패해도 나머지는 실행되고, 재시도는 실패한 처리기만 다시 돈다."""
    recorder = Recorder()
    recorder.errors["first"] = RuntimeError("boom")
    delivery = sync_delivery(
        recorder, RetryPolicy(max_attempts=2, initial_interval=0.5)
    )
    event = OrderPlaced(order="o-1")

    outcome = delivery.deliver(event)

    assert recorder.calls == ["first", "second"]
    assert isinstance(outcome, DeliveryRetry)
    assert outcome.state == DeliveryState(attempt=2, pending=frozenset({"first"}))
    assert outcome.delay == 0.5
    assert outcome.failures[0].exception_type == "RuntimeError"

    recorder.calls.clear()
    final = delivery.deliver(event, outcome.state)

    assert recorder.calls == ["first"]
    assert isinstance(final, DeliveryDeadLettered)
    assert final.dead_letter.subscriber == "billing"
    assert final.dead_letter.event_name == "OrderPlaced"
    assert final.dead_letter.attempts == 2
    assert final.dead_letter.pending == frozenset({"first"})
    assert final.dead_letter.failures[0].exception_message == "boom"


def test_sync_delivery_non_retryable_failure_expect_dead_letter_without_retry() -> None:
    """재시도로 고칠 수 없는 실패는 남은 횟수와 상관없이 바로 dead-letter다."""
    recorder = Recorder()
    recorder.errors["second"] = PermanentFailure()
    outcome = sync_delivery(recorder, RetryPolicy(max_attempts=5)).deliver(
        OrderPlaced(order="o-1")
    )
    assert isinstance(outcome, DeliveryDeadLettered)
    assert outcome.dead_letter.failures[0].retryable is False
    assert outcome.dead_letter.attempts == 1


def test_sync_delivery_deferral_expect_wait_without_counting_attempt() -> None:
    """지연 요청만 있으면 시도 횟수를 세지 않고 기다린다."""
    recorder = Recorder()
    recorder.errors["first"] = EventDeferredError(4.0)
    outcome = sync_delivery(recorder, RetryPolicy()).deliver(OrderPlaced(order="o-1"))
    assert outcome == DeliveryDeferred(
        state=DeliveryState(attempt=1, pending=frozenset({"first"})), retry_after=4.0
    )


def test_sync_delivery_deferral_with_failure_expect_wait_without_counting() -> None:
    """지연 요청과 재시도 가능한 실패가 섞이면 시도 횟수를 세지 않고 함께 기다린다."""
    recorder = Recorder()
    recorder.errors["first"] = EventDeferredError(4.0)
    recorder.errors["second"] = RuntimeError("boom")
    outcome = sync_delivery(recorder, RetryPolicy()).deliver(OrderPlaced(order="o-1"))
    assert outcome == DeliveryDeferred(
        state=DeliveryState(attempt=1, pending=frozenset({"first", "second"})),
        retry_after=4.0,
    )


@pytest.mark.parametrize("sibling", [EventDeferredError(4.0), RuntimeError("boom")])
def test_sync_delivery_non_retryable_with_sibling_expect_dead_letter_at_once(
    sibling: Exception,
) -> None:
    """재시도 불가 실패가 있으면 다른 처리기의 지연·실패와 상관없이 바로 dead-letter다."""
    recorder = Recorder()
    recorder.errors["first"] = sibling
    recorder.errors["second"] = PermanentFailure()
    outcome = sync_delivery(recorder, RetryPolicy(max_attempts=5)).deliver(
        OrderPlaced(order="o-1")
    )
    assert isinstance(outcome, DeliveryDeadLettered)
    assert outcome.dead_letter.pending == frozenset({"first", "second"})
    assert outcome.dead_letter.attempts == 1


@pytest.mark.parametrize(
    "error", [AuthContextNotFoundError(), AuthRequirementDeniedError()]
)
def test_sync_delivery_auth_refusal_expect_handler_skipped(error: Exception) -> None:
    """인가 거부는 재시도해도 같은 판정이라 그 처리기만 건너뛴다."""
    recorder = Recorder()
    recorder.errors["first"] = error
    outcome = sync_delivery(recorder, RetryPolicy()).deliver(OrderPlaced(order="o-1"))
    assert outcome == DeliveryCompleted()
    assert recorder.calls == ["first", "second"]


@pytest.mark.parametrize(
    "error",
    [
        AuthVerificationProviderUnavailableError(),
        AuthRequirementProviderUnavailableError(),
    ],
)
def test_sync_delivery_auth_provider_outage_expect_propagated(error: Exception) -> None:
    """인증 기반 장애는 메시지에 대한 판정이 아니므로 그대로 올라간다."""
    recorder = Recorder()
    recorder.errors["first"] = error
    with pytest.raises(type(error)):
        sync_delivery(recorder, RetryPolicy()).deliver(OrderPlaced(order="o-1"))
    assert EventDeliveryContext.current_or_none() is None


def test_sync_delivery_invoker_expect_adapter_controls_the_call() -> None:
    """어댑터는 invoker로 처리기 호출 방식을 바꿀 수 있다."""
    recorder = Recorder()
    invoked: list[str] = []

    def invoker(handler, event) -> None:
        invoked.append(handler.name)
        handler.callback(event)

    outcome = sync_delivery(recorder, RetryPolicy()).deliver(
        OrderPlaced(order="o-1"), invoker=invoker
    )
    assert outcome == DeliveryCompleted()
    assert invoked == recorder.calls == ["first", "second"]


def test_sync_delivery_registration_expect_unique_names_and_valid_subscriber() -> None:
    """한 구독 안의 처리기 이름은 유일하고, 구독자 이름은 검증된다."""
    delivery = sync_delivery(Recorder(), RetryPolicy())
    with pytest.raises(DuplicateEventHandlerNameError) as caught:
        delivery.add("first", lambda event: None)
    assert (caught.value.subscriber, caught.value.handler_name) == ("billing", "first")
    with pytest.raises(InvalidSubscriberNameError) as invalid:
        SubscriptionDelivery(OrderPlaced, "bill.ing", RetryPolicy())
    assert invalid.value.subscriber == "bill.ing"


async def test_async_delivery_all_succeed_expect_completed_with_context() -> None:
    """비동기 처리기도 같은 계약으로 완료된다."""
    recorder = Recorder()
    event = OrderPlaced(order="o-1")
    outcome = await async_delivery(recorder, RetryPolicy(), None).deliver(event)
    assert outcome == DeliveryCompleted()
    assert [(c.subscriber, c.handler) for c in recorder.contexts] == [
        ("", "first"),
        ("", "second"),
    ]
    assert EventDeliveryContext.current_or_none() is None


async def test_async_delivery_one_fails_expect_only_failed_retried_then_dead_letter() -> (
    None
):
    """비동기에서도 실패한 처리기만 재시도되고, 소진되면 dead-letter다."""
    recorder = Recorder()
    recorder.errors["first"] = RuntimeError("boom")
    delivery = async_delivery(recorder, RetryPolicy(max_attempts=2))
    event = OrderPlaced(order="o-1")

    outcome = await delivery.deliver(event)

    assert isinstance(outcome, DeliveryRetry)
    assert outcome.state.pending == frozenset({"first"})
    recorder.calls.clear()
    final = await delivery.deliver(event, outcome.state)
    assert recorder.calls == ["first"]
    assert isinstance(final, DeliveryDeadLettered)
    assert final.dead_letter.attempts == 2


async def test_async_delivery_deferral_and_auth_refusal_expect_same_contract() -> None:
    """비동기에서도 지연은 기다리고 인가 거부는 건너뛴다."""
    recorder = Recorder()
    recorder.errors["first"] = EventDeferredError(2.0)
    recorder.errors["second"] = AuthRequirementDeniedError()
    outcome = await async_delivery(recorder, RetryPolicy()).deliver(
        OrderPlaced(order="o-1")
    )
    assert isinstance(outcome, DeliveryDeferred)
    assert outcome.retry_after == 2.0


async def test_async_delivery_auth_provider_outage_expect_propagated() -> None:
    """비동기에서도 인증 기반 장애는 그대로 올라간다."""
    recorder = Recorder()
    recorder.errors["first"] = AuthVerificationProviderUnavailableError()
    with pytest.raises(AuthVerificationProviderUnavailableError):
        await async_delivery(recorder, RetryPolicy()).deliver(OrderPlaced(order="o-1"))


async def test_async_delivery_invoker_and_duplicate_name_expect_contract() -> None:
    """비동기 어댑터도 invoker를 쓰고, 이름 중복은 거부된다."""
    recorder = Recorder()
    delivery = async_delivery(recorder, RetryPolicy())
    invoked: list[str] = []

    async def invoker(handler, event) -> None:
        invoked.append(handler.name)
        await handler.callback(event)

    assert await delivery.deliver(OrderPlaced(order="o-1"), invoker=invoker) == (
        DeliveryCompleted()
    )
    assert invoked == ["first", "second"]
    with pytest.raises(DuplicateEventHandlerNameError):
        delivery.add("second", recorder.asynchronous("second"))


def test_event_subscriptions_expect_keyed_by_subscriber_and_event() -> None:
    """구독은 (구독자, 이벤트)마다 따로 모인다."""
    recorder = Recorder()
    subscriptions = EventSubscriptions(RetryPolicy(max_attempts=3))
    billing = subscriptions.register(
        OrderPlaced, recorder.sync("a"), "billing", "charge"
    )
    assert subscriptions.register(OrderPlaced, recorder.sync("b"), "billing") is billing
    unnamed = subscriptions.register(OrderPlaced, recorder.sync("c"))
    assert [handler.name for handler in billing.handlers] == ["charge", "OrderPlaced#1"]
    assert unnamed.subscriber is None and unnamed.policy.max_attempts == 3
    assert subscriptions.get("billing", OrderPlaced) is billing
    assert list(subscriptions) == [billing, unnamed]
    assert len(subscriptions) == 2
    with pytest.raises(SubscriptionNotFoundError) as caught:
        subscriptions.get("shipping", OrderPlaced)
    assert (caught.value.subscriber, caught.value.event_type) == (
        "shipping",
        OrderPlaced,
    )


def test_async_event_subscriptions_expect_keyed_by_subscriber_and_event() -> None:
    """비동기 구독도 (구독자, 이벤트)마다 따로 모인다."""
    recorder = Recorder()
    subscriptions = AsyncEventSubscriptions(RetryPolicy())
    billing = subscriptions.register(
        OrderPlaced, recorder.asynchronous("a"), "billing", "charge"
    )
    assert (
        subscriptions.register(OrderPlaced, recorder.asynchronous("b"), "billing")
        is billing
    )
    unnamed = subscriptions.register(OrderPlaced, recorder.asynchronous("c"))
    assert [handler.name for handler in billing.handlers] == ["charge", "OrderPlaced#1"]
    assert subscriptions.get(None, OrderPlaced) is unnamed
    assert list(subscriptions) == [billing, unnamed]
    assert len(subscriptions) == 2
    with pytest.raises(SubscriptionNotFoundError):
        subscriptions.get("shipping", OrderPlaced)


def test_event_routing_and_subscriber_key_expect_stable_names() -> None:
    """이벤트 라우팅 이름과 구독자 키는 타입만으로 정해진다."""
    assert EventRouting.name_of(OrderPlaced) == "OrderPlaced"
    assert SubscriberNames.key(None) == ""
    assert SubscriberNames.key("billing") == "billing"
    assert SubscriberNames.validate("billing-v2_a") == "billing-v2_a"


@pytest.mark.parametrize("name", ["dlq", "dlt", "retry", "redrive", "DLQ"])
def test_subscriber_name_reserved_for_broker_resources_expect_rejected(
    name: str,
) -> None:
    """dead-letter·재시도 자원 접미사와 같은 구독자 이름은 거부한다."""
    with pytest.raises(InvalidSubscriberNameError):
        SubscriberNames.validate(name)


async def test_delivery_pending_handler_missing_expect_dead_letter_not_completed() -> (
    None
):
    """남은 처리기가 더 이상 등록돼 있지 않으면 완료가 아니라 실패로 남긴다."""
    state = DeliveryState(pending=frozenset({"renamed", "second"}))
    event = OrderPlaced(order="o-1")
    recorder = Recorder()

    outcome = sync_delivery(recorder, RetryPolicy(max_attempts=5)).deliver(event, state)
    async_outcome = await async_delivery(recorder, RetryPolicy(max_attempts=5)).deliver(
        event, state
    )

    assert recorder.calls == ["second", "second"]
    for settled in (outcome, async_outcome):
        assert isinstance(settled, DeliveryDeadLettered)
        (failure,) = settled.dead_letter.failures
        assert failure.handler == "renamed"
        assert failure.exception_type == "EventHandlerNotRegisteredError"
        assert failure.retryable is False
