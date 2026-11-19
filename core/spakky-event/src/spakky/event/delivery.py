"""Broker-neutral delivery contract every integration event consumer implements.

The contract fixes what running the handlers of one subscriber means, so Kafka,
RabbitMQ and the in-memory broker behave the same way:

- every handler of the subscriber runs even when an earlier one fails;
- a delivery is retried while a failed handler remains, and a retry runs only
  the handlers that have not succeeded yet; a pending handler that is no
  longer registered counts as a non-retryable failure, never as done;
- retries are limited by `RetryPolicy`; a message that exhausts them, or that
  has a failure retrying cannot fix, moves to the subscriber's dead-letter
  destination together with `DeadLetter` metadata;
- a handler asking to wait (`EventDeferredError`) makes the delivery wait
  without counting an attempt, unless another handler failed for good;
- a dead letter is redriven to the subscriber it failed for, and to no other;
- an unavailable auth provider is no verdict about the message: the error
  leaves `deliver`, and the adapter must keep the message unacknowledged.

A broker adapter maps the returned `DeliveryOutcome` onto its own mechanics
(offset commit, ack, pause, retry destination, dead-letter destination).
"""

from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from logging import getLogger
from typing import Any, ClassVar, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from spakky.auth import (
    AuthContextNotFoundError,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
    AuthVerificationProviderUnavailableError,
)
from spakky.domain.models.event import AbstractEvent

from spakky.event.error import (
    AbstractNonRetryableEventError,
    EventDeferredError,
    EventDeliveryContextUnavailableError,
    EventHandlerNotRegisteredError,
    InvalidDeliveryHeaderError,
    SubscriptionNotFoundError,
)
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
)

# RetryMode and RetryPolicy lived here before spakky.event.retry; the redundant
# aliases keep ``from spakky.event.delivery import RetryMode`` working.
from spakky.event.retry import RetryMode as RetryMode
from spakky.event.retry import RetryPolicy as RetryPolicy
from spakky.event.subscription import (
    ConflictingSubscriberRetryPolicyError,
    DuplicateEventHandlerNameError,
    HandlerName,
    SubscriberName,
    SubscriberNames,
)

logger = getLogger(__name__)

type RetryPolicyResolver = Callable[
    [SubscriberName | None, RetryPolicy | None], RetryPolicy
]
"""Turns a subscriber and the retry its handlers declared into the policy it uses.

The declared retry is None when no handler class of the subscriber declared one.
"""

type DeliveryHeaders = Mapping[str, str]
"""String-valued message headers as every broker adapter exposes them."""


class DeliveryHeader(StrEnum):
    """Headers that carry retry state with a message set aside for a retry."""

    ATTEMPT = "x-spakky-delivery-attempt"
    PENDING_HANDLERS = "x-spakky-delivery-pending-handlers"
    NOT_BEFORE = "x-spakky-delivery-not-before"


class DeadLetterHeader(StrEnum):
    """Headers every dead-lettered message carries, on every broker."""

    ORIGINAL_DESTINATION = "x-spakky-dead-letter-original-destination"
    SUBSCRIBER = "x-spakky-dead-letter-subscriber"
    FAILURES = "x-spakky-dead-letter-failures"
    ATTEMPTS = "x-spakky-dead-letter-attempts"
    FAILED_AT = "x-spakky-dead-letter-failed-at"


class DeliveryState(BaseModel):
    """Where one message stands in its retry sequence for one subscriber."""

    model_config = ConfigDict(frozen=True)

    attempt: int = Field(default=1, ge=1)
    """1-based number of the attempt about to run."""

    pending: frozenset[HandlerName] | None = None
    """Handlers still to run; None means every handler (first delivery)."""

    _PENDING_ADAPTER: ClassVar[TypeAdapter[frozenset[HandlerName]]] = TypeAdapter(
        frozenset[HandlerName]
    )

    def to_headers(self) -> dict[str, str]:
        """Encode the state so it can travel with a message set aside for retry."""
        headers = {DeliveryHeader.ATTEMPT.value: str(self.attempt)}
        if self.pending is not None:
            headers[DeliveryHeader.PENDING_HANDLERS.value] = (
                self._PENDING_ADAPTER.dump_json(self.pending).decode()
            )
        return headers

    @classmethod
    def from_headers(cls, headers: DeliveryHeaders) -> Self:
        """Decode the state of a message; absent headers mean a first delivery.

        Raises:
            InvalidDeliveryHeaderError: A present header cannot be decoded.
        """
        pending = headers.get(DeliveryHeader.PENDING_HANDLERS.value)
        try:
            return cls(
                attempt=int(headers.get(DeliveryHeader.ATTEMPT.value, "1")),
                pending=(
                    None
                    if pending is None
                    else cls._PENDING_ADAPTER.validate_json(pending)
                ),
            )
        except (ValueError, ValidationError) as error:
            raise InvalidDeliveryHeaderError() from error


class HandlerFailure(BaseModel):
    """Why one handler did not complete in the last attempt."""

    model_config = ConfigDict(frozen=True)

    handler: HandlerName
    exception_type: str
    exception_message: str
    retryable: bool


class DeadLetter(BaseModel):
    """Metadata stored with a message a subscriber gave up on."""

    model_config = ConfigDict(frozen=True)

    event_name: str
    """Destination (topic, routing key) the message was originally published to."""

    subscriber: SubscriberName | None
    """Subscriber the message failed for; None is the unnamed subscriber."""

    failures: tuple[HandlerFailure, ...]
    """Handlers that had not succeeded when the subscriber gave up."""

    attempts: int
    """Number of delivery attempts made before giving up."""

    failed_at: datetime
    """When the last attempt ended."""

    _FAILURES_ADAPTER: ClassVar[TypeAdapter[tuple[HandlerFailure, ...]]] = TypeAdapter(
        tuple[HandlerFailure, ...]
    )

    @property
    def pending(self) -> frozenset[HandlerName]:
        """Handlers a redrive has to run."""
        return frozenset(failure.handler for failure in self.failures)

    def to_headers(self) -> dict[str, str]:
        """Encode the metadata as dead-letter message headers."""
        return {
            DeadLetterHeader.ORIGINAL_DESTINATION.value: self.event_name,
            DeadLetterHeader.SUBSCRIBER.value: SubscriberNames.key(self.subscriber),
            DeadLetterHeader.FAILURES.value: self._FAILURES_ADAPTER.dump_json(
                self.failures
            ).decode(),
            DeadLetterHeader.ATTEMPTS.value: str(self.attempts),
            DeadLetterHeader.FAILED_AT.value: self.failed_at.isoformat(),
        }

    @classmethod
    def from_headers(cls, headers: DeliveryHeaders) -> Self:
        """Decode dead-letter metadata from message headers.

        Raises:
            InvalidDeliveryHeaderError: A header is absent or cannot be decoded.
        """
        try:
            subscriber = headers[DeadLetterHeader.SUBSCRIBER.value]
            return cls(
                event_name=headers[DeadLetterHeader.ORIGINAL_DESTINATION.value],
                subscriber=subscriber or None,
                failures=cls._FAILURES_ADAPTER.validate_json(
                    headers[DeadLetterHeader.FAILURES.value]
                ),
                attempts=int(headers[DeadLetterHeader.ATTEMPTS.value]),
                failed_at=datetime.fromisoformat(
                    headers[DeadLetterHeader.FAILED_AT.value]
                ),
            )
        except (KeyError, ValueError, ValidationError) as error:
            raise InvalidDeliveryHeaderError() from error


class DeliveryCompleted(BaseModel):
    """Every handler is done; the adapter acknowledges the message."""

    model_config = ConfigDict(frozen=True)


class DeliveryRetry(BaseModel):
    """A handler failed and attempts remain; deliver again after `delay`."""

    model_config = ConfigDict(frozen=True)

    state: DeliveryState
    delay: float
    failures: tuple[HandlerFailure, ...]


class DeliveryDeferred(BaseModel):
    """A handler asked to wait; deliver again without counting an attempt."""

    model_config = ConfigDict(frozen=True)

    state: DeliveryState
    retry_after: float


class DeliveryDeadLettered(BaseModel):
    """The subscriber gave up; the adapter stores the message as a dead letter."""

    model_config = ConfigDict(frozen=True)

    dead_letter: DeadLetter


type DeliveryOutcome = (
    DeliveryCompleted | DeliveryRetry | DeliveryDeferred | DeliveryDeadLettered
)
"""What one delivery attempt settled; adapters map it onto broker mechanics."""


class EventDeliveryContext(BaseModel):
    """Identity of the handler call a consumer is making right now.

    Set around every handler invocation so that cross-cutting code, such as the
    idempotency aspect, can key its records without the handler passing it on.
    """

    model_config = ConfigDict(frozen=True)

    subscriber: SubscriberName
    """Subscriber key; the unnamed subscriber is the empty string."""

    handler: HandlerName
    event_id: UUID
    attempt: int

    _CURRENT: ClassVar[ContextVar["EventDeliveryContext | None"]] = ContextVar(
        "spakky_event_delivery_context", default=None
    )

    def activate(self) -> Token["EventDeliveryContext | None"]:
        """Mark this delivery as the one in progress until `deactivate`."""
        return self._CURRENT.set(self)

    @classmethod
    def deactivate(cls, token: Token["EventDeliveryContext | None"]) -> None:
        """Restore whatever delivery was in progress before `activate`."""
        cls._CURRENT.reset(token)

    @classmethod
    def current(cls) -> "EventDeliveryContext":
        """Return the delivery in progress.

        Raises:
            EventDeliveryContextUnavailableError: No consumer is delivering.
        """
        context = cls._CURRENT.get()
        if context is None:
            raise EventDeliveryContextUnavailableError()
        return context

    @classmethod
    def current_or_none(cls) -> "EventDeliveryContext | None":
        """Return the delivery in progress, or None outside a consumer call."""
        return cls._CURRENT.get()


@dataclass(frozen=True, slots=True)
class RegisteredEventHandler[CallbackT]:
    """One named handler of a subscription."""

    name: HandlerName
    callback: CallbackT


@dataclass(slots=True)
class DeliveryAttempt:
    """Mutable tally of one delivery attempt, settled into a `DeliveryOutcome`."""

    event_name: str
    subscriber: SubscriberName | None
    policy: RetryPolicy
    state: DeliveryState
    failures: list[HandlerFailure]
    deferred: list[HandlerName]
    retry_after: float

    def record_failure(self, handler: HandlerName, error: Exception) -> None:
        """Keep a handler failure for the retry decision and dead-letter metadata."""
        self.failures.append(
            HandlerFailure(
                handler=handler,
                exception_type=type(error).__qualname__,
                exception_message=str(error),
                retryable=not isinstance(error, AbstractNonRetryableEventError),
            )
        )

    def record_deferral(self, handler: HandlerName, error: EventDeferredError) -> None:
        """Keep a handler's request to be delivered again later."""
        self.deferred.append(handler)
        self.retry_after = max(self.retry_after, error.retry_after)
        self.failures.append(
            HandlerFailure(
                handler=handler,
                exception_type=type(error).__qualname__,
                exception_message=str(error),
                retryable=True,
            )
        )

    def settle(self) -> DeliveryOutcome:
        """Turn the tally into the outcome the broker adapter has to act on.

        One message gets one outcome, so mixed handler results follow a fixed
        precedence: a non-retryable failure dead-letters the delivery at once,
        otherwise a deferral makes the whole delivery wait without counting an
        attempt, otherwise the failures are retried while attempts remain. In
        every case the handlers that have not succeeded stay pending together.
        """
        if not self.failures:
            return DeliveryCompleted()
        pending = frozenset(failure.handler for failure in self.failures)
        fatal = any(not failure.retryable for failure in self.failures)
        if self.deferred and not fatal:
            return DeliveryDeferred(
                state=DeliveryState(attempt=self.state.attempt, pending=pending),
                retry_after=self.retry_after,
            )
        if not fatal and self.state.attempt < self.policy.max_attempts:
            return DeliveryRetry(
                state=DeliveryState(attempt=self.state.attempt + 1, pending=pending),
                delay=self.policy.delay_after(self.state.attempt),
                failures=tuple(self.failures),
            )
        return DeliveryDeadLettered(
            dead_letter=DeadLetter(
                event_name=self.event_name,
                subscriber=self.subscriber,
                failures=tuple(self.failures),
                attempts=self.state.attempt,
                failed_at=datetime.now(UTC),
            )
        )


class SubscriptionDelivery:
    """Runs the sync handlers one subscriber registered for one event type."""

    event_type: type[AbstractEvent]
    subscriber: SubscriberName | None
    policy: RetryPolicy
    # Any: handlers of one subscription are registered per concrete event type,
    # but the callback's parameter type is erased once they share a list.
    handlers: list[RegisteredEventHandler[EventHandlerCallback[Any]]]

    def __init__(
        self,
        event_type: type[AbstractEvent],
        subscriber: SubscriberName | None,
        policy: RetryPolicy,
    ) -> None:
        self.event_type = event_type
        self.subscriber = SubscriberNames.validate(subscriber)
        self.policy = policy
        self.handlers = []

    def add(self, name: HandlerName, callback: EventHandlerCallback[Any]) -> None:
        """Add a handler under a name unique within this subscription.

        Raises:
            DuplicateEventHandlerNameError: The name is already taken.
        """
        if any(handler.name == name for handler in self.handlers):
            raise DuplicateEventHandlerNameError(self.subscriber, name)
        self.handlers.append(RegisteredEventHandler(name=name, callback=callback))

    def deliver(
        self,
        event: AbstractEvent,
        state: DeliveryState | None = None,
        invoker: Callable[
            [RegisteredEventHandler[EventHandlerCallback[Any]], AbstractEvent], None
        ]
        | None = None,
    ) -> DeliveryOutcome:
        """Run every pending handler once and settle the attempt.

        Args:
            event: Deserialized event to hand to the handlers.
            state: Retry state of the message; None means a first delivery.
            invoker: Adapter hook that calls a handler with adapter-specific
                arguments; None calls `handler.callback(event)`.

        Returns:
            What the adapter must do with the message.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable; the message must stay unacknowledged.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable; the message must stay unacknowledged.
        """
        current = DeliveryState() if state is None else state
        attempt = DeliveryAttempt(
            event_name=event.event_name,
            subscriber=self.subscriber,
            policy=self.policy,
            state=current,
            failures=[],
            deferred=[],
            retry_after=0.0,
        )
        for missing in sorted(
            (current.pending or frozenset())
            - {handler.name for handler in self.handlers}
        ):
            # 이름이 바뀌거나 사라진 처리기를 완료로 치면 메시지가 실행 없이 버려진다.
            attempt.record_failure(missing, EventHandlerNotRegisteredError())
        for handler in self.handlers:
            if current.pending is not None and handler.name not in current.pending:
                continue
            token = EventDeliveryContext(
                subscriber=SubscriberNames.key(self.subscriber),
                handler=handler.name,
                event_id=event.event_id,
                attempt=current.attempt,
            ).activate()
            try:
                if invoker is None:
                    handler.callback(event)
                else:
                    invoker(handler, event)
            except EventDeferredError as error:
                attempt.record_deferral(handler.name, error)
            except (
                AuthVerificationProviderUnavailableError,
                AuthRequirementProviderUnavailableError,
            ):
                # 인증 기반이 내려간 것은 이 메시지에 대한 판정이 아니다.
                raise
            except (AuthContextNotFoundError, AuthRequirementDeniedError) as error:
                # 인가 거부는 같은 메시지를 다시 보내도 바뀌지 않는 판정이다.
                logger.warning(
                    f"Auth boundary refused {event.event_name} for handler "
                    f"{handler.name}, skipping it: {error}"
                )
            except Exception as error:
                logger.warning(
                    f"Handler {handler.name} failed for {event.event_name} "
                    f"(attempt {current.attempt}): {error}"
                )
                attempt.record_failure(handler.name, error)
            finally:
                EventDeliveryContext.deactivate(token)
        return attempt.settle()


class AsyncSubscriptionDelivery:
    """Runs the async handlers one subscriber registered for one event type."""

    event_type: type[AbstractEvent]
    subscriber: SubscriberName | None
    policy: RetryPolicy
    # Any: handlers of one subscription are registered per concrete event type,
    # but the callback's parameter type is erased once they share a list.
    handlers: list[RegisteredEventHandler[AsyncEventHandlerCallback[Any]]]

    def __init__(
        self,
        event_type: type[AbstractEvent],
        subscriber: SubscriberName | None,
        policy: RetryPolicy,
    ) -> None:
        self.event_type = event_type
        self.subscriber = SubscriberNames.validate(subscriber)
        self.policy = policy
        self.handlers = []

    def add(self, name: HandlerName, callback: AsyncEventHandlerCallback[Any]) -> None:
        """Add a handler under a name unique within this subscription.

        Raises:
            DuplicateEventHandlerNameError: The name is already taken.
        """
        if any(handler.name == name for handler in self.handlers):
            raise DuplicateEventHandlerNameError(self.subscriber, name)
        self.handlers.append(RegisteredEventHandler(name=name, callback=callback))

    async def deliver(
        self,
        event: AbstractEvent,
        state: DeliveryState | None = None,
        invoker: Callable[
            [RegisteredEventHandler[AsyncEventHandlerCallback[Any]], AbstractEvent],
            Awaitable[None],
        ]
        | None = None,
    ) -> DeliveryOutcome:
        """Run every pending handler once and settle the attempt.

        Args:
            event: Deserialized event to hand to the handlers.
            state: Retry state of the message; None means a first delivery.
            invoker: Adapter hook that calls a handler with adapter-specific
                arguments; None awaits `handler.callback(event)`.

        Returns:
            What the adapter must do with the message.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable; the message must stay unacknowledged.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable; the message must stay unacknowledged.
        """
        current = DeliveryState() if state is None else state
        attempt = DeliveryAttempt(
            event_name=event.event_name,
            subscriber=self.subscriber,
            policy=self.policy,
            state=current,
            failures=[],
            deferred=[],
            retry_after=0.0,
        )
        for missing in sorted(
            (current.pending or frozenset())
            - {handler.name for handler in self.handlers}
        ):
            # 이름이 바뀌거나 사라진 처리기를 완료로 치면 메시지가 실행 없이 버려진다.
            attempt.record_failure(missing, EventHandlerNotRegisteredError())
        for handler in self.handlers:
            if current.pending is not None and handler.name not in current.pending:
                continue
            token = EventDeliveryContext(
                subscriber=SubscriberNames.key(self.subscriber),
                handler=handler.name,
                event_id=event.event_id,
                attempt=current.attempt,
            ).activate()
            try:
                if invoker is None:
                    await handler.callback(event)
                else:
                    await invoker(handler, event)
            except EventDeferredError as error:
                attempt.record_deferral(handler.name, error)
            except (
                AuthVerificationProviderUnavailableError,
                AuthRequirementProviderUnavailableError,
            ):
                # 인증 기반이 내려간 것은 이 메시지에 대한 판정이 아니다.
                raise
            except (AuthContextNotFoundError, AuthRequirementDeniedError) as error:
                # 인가 거부는 같은 메시지를 다시 보내도 바뀌지 않는 판정이다.
                logger.warning(
                    f"Auth boundary refused {event.event_name} for handler "
                    f"{handler.name}, skipping it: {error}"
                )
            except Exception as error:
                logger.warning(
                    f"Handler {handler.name} failed for {event.event_name} "
                    f"(attempt {current.attempt}): {error}"
                )
                attempt.record_failure(handler.name, error)
            finally:
                EventDeliveryContext.deactivate(token)
        return attempt.settle()


class EventSubscriptions:
    """Sync subscriptions of one consumer, keyed by subscriber and event type.

    Every subscription of one subscriber shares that subscriber's retry policy,
    because one worker serves all of its events.
    """

    policy: RetryPolicy
    """Consumer-wide retry every subscriber starts from."""

    _resolver: RetryPolicyResolver
    _declared: dict[SubscriberName | None, RetryPolicy]
    """Retry each subscriber's handler classes declared; absent when none did."""

    _deliveries: dict[
        tuple[SubscriberName | None, type[AbstractEvent]], SubscriptionDelivery
    ]

    def __init__(
        self, policy: RetryPolicy, resolver: RetryPolicyResolver | None = None
    ) -> None:
        """Create an empty registry.

        Args:
            policy: Consumer-wide retry every subscriber starts from.
            resolver: Turns a subscriber and its declared retry into the policy
                it uses. None overlays the declared retry on `policy`.
        """
        self.policy = policy
        self._resolver = resolver if resolver is not None else self._overlay_declared
        self._declared = {}
        self._deliveries = {}

    def _overlay_declared(
        self, subscriber: SubscriberName | None, declared: RetryPolicy | None
    ) -> RetryPolicy:
        """Default resolver: the declared fields over the consumer-wide policy."""
        return self.policy.overlay(declared)

    def policy_of(self, subscriber: SubscriberName | None) -> RetryPolicy:
        """Return the retry policy `subscriber` uses for every event it reads."""
        return self._resolver(subscriber, self._declared.get(subscriber))

    def _declare(self, subscriber: SubscriberName | None, retry: RetryPolicy) -> None:
        """Record the retry a handler class of `subscriber` declared.

        Raises:
            ConflictingSubscriberRetryPolicyError: Another handler class of the
                subscriber declared a different retry.
        """
        known = self._declared.get(subscriber)
        if known is not None:
            if not known.declares_same(retry):
                raise ConflictingSubscriberRetryPolicyError(subscriber)
            return
        self._declared[subscriber] = retry
        # 먼저 등록된, retry를 선언하지 않은 클래스의 구독도 새 policy를 따른다.
        policy = self.policy_of(subscriber)
        for delivery in self._deliveries.values():
            if delivery.subscriber == subscriber:
                delivery.policy = policy

    def register(
        self,
        event: type[AbstractEvent],
        handler: EventHandlerCallback[Any],
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
        retry: RetryPolicy | None = None,
    ) -> SubscriptionDelivery:
        """Add a handler to the subscription of `subscriber` for `event`.

        Args:
            event: Event type the handler receives.
            handler: Callback invoked with the deserialized event.
            subscriber: Subscriber the handler belongs to; None is unnamed.
            handler_name: Stable name inside the subscription. None derives a
                positional name, which is not stable enough for idempotency.
            retry: Retry the handler's class declared for its subscriber; None
                follows whatever the subscriber's other classes declared.

        Returns:
            The subscription the handler was added to.

        Raises:
            InvalidSubscriberNameError: The subscriber name is unusable.
            ConflictingSubscriberRetryPolicyError: Another handler class of the
                subscriber declared a different retry.
        """
        SubscriberNames.validate(subscriber)
        if retry is not None:
            self._declare(subscriber, retry)
        key = (subscriber, event)
        delivery = self._deliveries.get(key)
        if delivery is None:
            delivery = SubscriptionDelivery(
                event, subscriber, self.policy_of(subscriber)
            )
            self._deliveries[key] = delivery
        delivery.add(
            handler_name
            if handler_name is not None
            else f"{event.__name__}#{len(delivery.handlers)}",
            handler,
        )
        return delivery

    def get(
        self, subscriber: SubscriberName | None, event: type[AbstractEvent]
    ) -> SubscriptionDelivery:
        """Return the subscription of `subscriber` for `event`.

        Raises:
            SubscriptionNotFoundError: Nothing is registered for the pair.
        """
        delivery = self._deliveries.get((subscriber, event))
        if delivery is None:
            raise SubscriptionNotFoundError(subscriber, event)
        return delivery

    def __iter__(self) -> Iterator[SubscriptionDelivery]:
        return iter(self._deliveries.values())

    def __len__(self) -> int:
        return len(self._deliveries)


class AsyncEventSubscriptions:
    """Async subscriptions of one consumer, keyed by subscriber and event type.

    Every subscription of one subscriber shares that subscriber's retry policy,
    because one worker serves all of its events.
    """

    policy: RetryPolicy
    """Consumer-wide retry every subscriber starts from."""

    _resolver: RetryPolicyResolver
    _declared: dict[SubscriberName | None, RetryPolicy]
    """Retry each subscriber's handler classes declared; absent when none did."""

    _deliveries: dict[
        tuple[SubscriberName | None, type[AbstractEvent]], AsyncSubscriptionDelivery
    ]

    def __init__(
        self, policy: RetryPolicy, resolver: RetryPolicyResolver | None = None
    ) -> None:
        """Create an empty registry.

        Args:
            policy: Consumer-wide retry every subscriber starts from.
            resolver: Turns a subscriber and its declared retry into the policy
                it uses. None overlays the declared retry on `policy`.
        """
        self.policy = policy
        self._resolver = resolver if resolver is not None else self._overlay_declared
        self._declared = {}
        self._deliveries = {}

    def _overlay_declared(
        self, subscriber: SubscriberName | None, declared: RetryPolicy | None
    ) -> RetryPolicy:
        """Default resolver: the declared fields over the consumer-wide policy."""
        return self.policy.overlay(declared)

    def policy_of(self, subscriber: SubscriberName | None) -> RetryPolicy:
        """Return the retry policy `subscriber` uses for every event it reads."""
        return self._resolver(subscriber, self._declared.get(subscriber))

    def _declare(self, subscriber: SubscriberName | None, retry: RetryPolicy) -> None:
        """Record the retry a handler class of `subscriber` declared.

        Raises:
            ConflictingSubscriberRetryPolicyError: Another handler class of the
                subscriber declared a different retry.
        """
        known = self._declared.get(subscriber)
        if known is not None:
            if not known.declares_same(retry):
                raise ConflictingSubscriberRetryPolicyError(subscriber)
            return
        self._declared[subscriber] = retry
        # 먼저 등록된, retry를 선언하지 않은 클래스의 구독도 새 policy를 따른다.
        policy = self.policy_of(subscriber)
        for delivery in self._deliveries.values():
            if delivery.subscriber == subscriber:
                delivery.policy = policy

    def register(
        self,
        event: type[AbstractEvent],
        handler: AsyncEventHandlerCallback[Any],
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
        retry: RetryPolicy | None = None,
    ) -> AsyncSubscriptionDelivery:
        """Add a handler to the subscription of `subscriber` for `event`.

        Args:
            event: Event type the handler receives.
            handler: Callback awaited with the deserialized event.
            subscriber: Subscriber the handler belongs to; None is unnamed.
            handler_name: Stable name inside the subscription. None derives a
                positional name, which is not stable enough for idempotency.
            retry: Retry the handler's class declared for its subscriber; None
                follows whatever the subscriber's other classes declared.

        Returns:
            The subscription the handler was added to.

        Raises:
            InvalidSubscriberNameError: The subscriber name is unusable.
            ConflictingSubscriberRetryPolicyError: Another handler class of the
                subscriber declared a different retry.
        """
        SubscriberNames.validate(subscriber)
        if retry is not None:
            self._declare(subscriber, retry)
        key = (subscriber, event)
        delivery = self._deliveries.get(key)
        if delivery is None:
            delivery = AsyncSubscriptionDelivery(
                event, subscriber, self.policy_of(subscriber)
            )
            self._deliveries[key] = delivery
        delivery.add(
            handler_name
            if handler_name is not None
            else f"{event.__name__}#{len(delivery.handlers)}",
            handler,
        )
        return delivery

    def get(
        self, subscriber: SubscriberName | None, event: type[AbstractEvent]
    ) -> AsyncSubscriptionDelivery:
        """Return the subscription of `subscriber` for `event`.

        Raises:
            SubscriptionNotFoundError: Nothing is registered for the pair.
        """
        delivery = self._deliveries.get((subscriber, event))
        if delivery is None:
            raise SubscriptionNotFoundError(subscriber, event)
        return delivery

    def __iter__(self) -> Iterator[AsyncSubscriptionDelivery]:
        return iter(self._deliveries.values())

    def __len__(self) -> int:
        return len(self._deliveries)


class EventRouting:
    """Routing identity of event types shared by publishers and consumers."""

    @staticmethod
    def name_of(event: type[AbstractEvent]) -> str:
        """Return the destination name an event type is published under.

        `event_name` is an instance property that subclasses may override with
        a class-static value, so it is read through an uninitialized instance.
        """
        probe = object.__new__(event)
        return probe.event_name
