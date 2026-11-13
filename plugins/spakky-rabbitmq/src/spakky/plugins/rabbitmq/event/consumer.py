"""RabbitMQ event consumers for integration events.

Provides synchronous and asynchronous event consumers that run as background
services. Each subscriber owns a queue of its own, and every message is handed
to the broker-neutral delivery contract of `spakky.event.delivery`, which decides
whether the message is acknowledged, retried or dead-lettered.
"""

from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import wait_for
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from logging import getLogger
from math import ceil
from typing import Any, cast, override

from aio_pika import (  # type: ignore[import-untyped]  # aio_pika lacks type stubs
    DeliveryMode,
    Message,
    connect_robust,
)
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractRobustConnection,
)
from aio_pika.exceptions import DeliveryError
from pika import URLParameters
from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection
from pika.exceptions import NackError, UnroutableError
from pika.spec import Basic, BasicProperties
from pydantic import TypeAdapter, ValidationError
from spakky.auth import (
    AuthorizationDecisionState,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
    AuthVerificationProviderUnavailableError,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.core.service.background import (
    AbstractAsyncBackgroundService,
    AbstractBackgroundService,
)
from spakky.domain.models.event import AbstractEvent, AbstractIntegrationEvent
from spakky.event.delivery import (
    AsyncEventSubscriptions,
    AsyncSubscriptionDelivery,
    DeadLetter,
    DeliveryCompleted,
    DeliveryDeadLettered,
    DeliveryOutcome,
    DeliveryRetry,
    DeliveryState,
    EventRouting,
    EventSubscriptions,
    HandlerFailure,
    RegisteredEventHandler,
    RetryMode,
    RetryPolicy,
    SubscriptionDelivery,
)
from spakky.event.error import InvalidDeliveryHeaderError, InvalidMessageError
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.redrive import IAsyncEventRedriver, IEventRedriver, RedriveResult
from spakky.event.subscription import HandlerName, SubscriberName
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

from spakky.plugins.rabbitmq.auth import (
    reset_current_rabbitmq_message_headers,
    set_current_rabbitmq_message_headers,
)
from spakky.plugins.rabbitmq.common.config import (
    RabbitMQAuthFailureAction,
    RabbitMQConnectionConfig,
)
from spakky.plugins.rabbitmq.common.constants import (
    BLOCKING_PREFETCH_COUNT,
    DEAD_LETTER_EXCHANGE_ARGUMENT,
    DEAD_LETTER_ROUTING_KEY_ARGUMENT,
    DEFAULT_EXCHANGE_NAME,
    MILLISECONDS_PER_SECOND,
    PERSISTENT_DELIVERY_MODE,
)
from spakky.plugins.rabbitmq.error import (
    RabbitMQAuthRequeueError,
    SubscriberExchangeRequiredError,
)
from spakky.plugins.rabbitmq.event.topology import (
    QueueName,
    RabbitMQSubscriptionQueues,
)

logger = getLogger(__name__)


@dataclass(slots=True)
class RabbitMQAuthSettlement:
    """What the auth failure policy asked for while one message was delivered."""

    drop: bool = False
    """A `nack_drop` policy applied; the message is rejected instead of acked."""


@Pod()
class RabbitMQEventConsumer(
    IIntegrationEventConsumer, IEventRedriver, AbstractBackgroundService
):
    """Synchronous RabbitMQ event consumer.

    Runs as a background service that consumes one durable queue per subscriber
    and delivers each message to that subscriber's synchronous handlers under
    the delivery contract: failed handlers are retried by `RetryPolicy`, and a
    message the subscriber gives up on moves to the subscriber's own
    dead-letter queue.

    Attributes:
        connection_string: AMQP connection string.
        exchange_name: Exchange subscriber queues are bound to, if configured.
        connection: Blocking RabbitMQ connection.
        channel: Blocking channel for message consumption.
        publish_channel: Confirm-mode channel for retry and dead-letter copies.
    """

    connection_string: str
    exchange_name: str | None
    connection: BlockingConnection
    channel: BlockingChannel
    publish_channel: BlockingChannel
    _retry: RetryPolicy
    _subscriptions: EventSubscriptions
    _adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    _propagator: ITracePropagator | None
    _auth_challenge_action: RabbitMQAuthFailureAction
    _auth_deny_action: RabbitMQAuthFailureAction
    _auth_error_action: RabbitMQAuthFailureAction

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the synchronous RabbitMQ event consumer.

        Args:
            config: RabbitMQ connection configuration.
        """
        super().__init__()
        self.connection_string = config.connection_string
        self.exchange_name = config.exchange_name
        self._retry = config.retry
        self._subscriptions = EventSubscriptions(config.retry)
        self._adapters = {}
        self._propagator = None
        self._auth_challenge_action = config.auth_challenge_action
        self._auth_deny_action = config.auth_deny_action
        self._auth_error_action = config.auth_error_action

    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: The trace propagator instance.
        """
        self._propagator = propagator

    @staticmethod
    def _to_string_headers(raw: Mapping[str, object] | None) -> dict[str, str]:
        """Convert AMQP headers to a string-valued carrier dict.

        AMQP headers may contain bytes values (RabbitMQ encodes strings as
        bytes). This method decodes bytes and keeps str values, skipping
        other types.

        Args:
            raw: Raw AMQP headers dict, or None.

        Returns:
            A dict with string keys and string values.
        """
        if raw is None or not isinstance(raw, Mapping):
            return {}
        result: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(value, str):
                result[key] = value
            elif isinstance(value, bytes):
                result[key] = value.decode()
        return result

    def _queues(self, delivery: SubscriptionDelivery) -> RabbitMQSubscriptionQueues:
        return RabbitMQSubscriptionQueues.of(
            EventRouting.name_of(delivery.event_type), delivery.subscriber
        )

    def _on_message(
        self,
        delivery: SubscriptionDelivery,
        queues: RabbitMQSubscriptionQueues,
        _channel: BlockingChannel,
        method_frame: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> None:
        """Deliver one incoming message to the subscriber that owns its queue."""
        if method_frame.consumer_tag is None or method_frame.delivery_tag is None:
            raise InvalidMessageError("Missing consumer tag or delivery tag.")
        self._settle(
            delivery,
            queues,
            method_frame.delivery_tag,
            self._to_string_headers(properties.headers),
            body,
            None,
        )

    def _settle(
        self,
        delivery: SubscriptionDelivery,
        queues: RabbitMQSubscriptionQueues,
        delivery_tag: int,
        carrier: dict[str, str],
        body: bytes,
        state: DeliveryState | None,
    ) -> None:
        """Run one delivery attempt and apply its outcome to the broker.

        Args:
            delivery: Subscription the message belongs to.
            queues: Queues owned by that subscription.
            delivery_tag: Tag of the still unacknowledged message.
            carrier: String-valued headers of the message.
            body: Serialized event payload.
            state: Retry state remembered from a blocking wait; None reads the
                state from the message headers.
        """
        try:
            outcome, drop = self._attempt(delivery, carrier, body, state)
        except (
            AuthVerificationProviderUnavailableError,
            AuthRequirementProviderUnavailableError,
        ) as error:
            # 인증 기반 장애는 메시지에 대한 판정이 아니므로 확인하지 않고 되돌린다.
            logger.warning(
                f"Auth is unavailable for {queues.queue}, requeueing the message: "
                f"{error}"
            )
            self.channel.basic_nack(delivery_tag, requeue=True)
            return
        if isinstance(outcome, DeliveryCompleted):
            if drop:
                self.channel.basic_nack(delivery_tag, requeue=False)
                return
            self.channel.basic_ack(delivery_tag)
            return
        if isinstance(outcome, DeliveryDeadLettered):
            self._forward(
                self.channel,
                self.publish_channel,
                delivery_tag,
                queues.dead_letter_queue,
                body,
                {**carrier, **outcome.dead_letter.to_headers()},
                None,
            )
            return
        delay = (
            outcome.delay if isinstance(outcome, DeliveryRetry) else outcome.retry_after
        )
        if self._retry.mode is RetryMode.DELAYED:
            self._forward(
                self.channel,
                self.publish_channel,
                delivery_tag,
                queues.retry_queue,
                body,
                {**carrier, **outcome.state.to_headers()},
                delay,
            )
            return
        # 메시지를 확인하지 않은 채 기다린다. prefetch 1이라 같은 큐의 다음
        # 메시지는 이 메시지가 끝날 때까지 전달되지 않는다.
        self.connection.call_later(
            delay,
            partial(
                self._redeliver,
                delivery,
                queues,
                delivery_tag,
                carrier,
                body,
                outcome.state,
            ),
        )

    def _redeliver(
        self,
        delivery: SubscriptionDelivery,
        queues: RabbitMQSubscriptionQueues,
        delivery_tag: int,
        carrier: dict[str, str],
        body: bytes,
        state: DeliveryState,
    ) -> None:
        """Deliver a message again once its blocking wait is over."""
        if self._stop_event.is_set():
            # 종료 중에는 다시 실행하지 않는다. 채널이 닫히면 브로커가 되돌린다.
            return
        self._settle(delivery, queues, delivery_tag, carrier, body, state)

    def _attempt(
        self,
        delivery: SubscriptionDelivery,
        carrier: dict[str, str],
        body: bytes,
        state: DeliveryState | None,
    ) -> tuple[DeliveryOutcome, bool]:
        """Deserialize a message and run the pending handlers once.

        Returns:
            The delivery outcome, and whether the auth policy asked to reject
            the message instead of acknowledging it.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable; the message must stay unacknowledged.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable, or the auth policy asked for a requeue.
        """
        if self._propagator is not None:
            parent = self._propagator.extract(carrier)
            ctx = parent.child() if parent is not None else TraceContext.new_root()
            TraceContext.set(ctx)
        token = set_current_rabbitmq_message_headers(carrier)
        auth = RabbitMQAuthSettlement()
        try:
            try:
                current = (
                    DeliveryState.from_headers(carrier) if state is None else state
                )
            except InvalidDeliveryHeaderError as error:
                return self._unprocessable(delivery, DeliveryState(), error), False
            try:
                event = self._adapters[delivery.event_type].validate_json(body)
            except ValidationError as error:
                return self._unprocessable(delivery, current, error), False
            outcome = delivery.deliver(event, current, partial(self._invoke, auth))
            return outcome, auth.drop
        finally:
            reset_current_rabbitmq_message_headers(token)
            if self._propagator is not None:
                TraceContext.clear()

    def _unprocessable(
        self,
        delivery: SubscriptionDelivery,
        state: DeliveryState,
        error: Exception,
    ) -> DeliveryDeadLettered:
        """Dead-letter a message no retry can turn into a handler call."""
        logger.warning(
            f"Message for {EventRouting.name_of(delivery.event_type)} cannot be "
            f"processed, dead-lettering it: {error}"
        )
        return DeliveryDeadLettered(
            dead_letter=DeadLetter(
                event_name=EventRouting.name_of(delivery.event_type),
                subscriber=delivery.subscriber,
                failures=tuple(
                    HandlerFailure(
                        handler=handler.name,
                        exception_type=type(error).__qualname__,
                        exception_message=str(error),
                        retryable=False,
                    )
                    for handler in delivery.handlers
                    if state.pending is None or handler.name in state.pending
                ),
                attempts=state.attempt,
                failed_at=datetime.now(UTC),
            )
        )

    def _invoke(
        self,
        auth: RabbitMQAuthSettlement,
        # Any: the delivery engine erases the concrete event type of callbacks.
        handler: RegisteredEventHandler[EventHandlerCallback[Any]],
        event: AbstractEvent,
    ) -> None:
        """Call a handler and map an auth denial onto the configured action."""
        try:
            handler.callback(event)
        except AuthRequirementDeniedError as error:
            action = self._auth_failure_action(error)
            if action is RabbitMQAuthFailureAction.NACK_REQUEUE:
                raise RabbitMQAuthRequeueError() from error
            if action is RabbitMQAuthFailureAction.NACK_DROP:
                auth.drop = True
            raise

    def _forward(
        self,
        channel: BlockingChannel,
        publish_channel: BlockingChannel,
        delivery_tag: int,
        queue: QueueName,
        body: bytes,
        headers: dict[str, str],
        delay: float | None,
    ) -> None:
        """Move a message to another queue of the subscriber.

        The original is acknowledged only after the broker confirmed the copy;
        otherwise it is requeued so that it cannot be lost.

        Args:
            channel: Channel the original message was received on.
            publish_channel: Confirm-mode channel of the same connection.
            delivery_tag: Tag of the original message.
            queue: Retry or dead-letter queue receiving the copy.
            body: Serialized event payload.
            headers: Headers of the copy, including retry or dead-letter state.
            delay: Seconds the copy waits before it expires back into the
                subscriber queue; None stores it without expiration.
        """
        try:
            publish_channel.basic_publish(
                DEFAULT_EXCHANGE_NAME,
                queue,
                body,
                properties=BasicProperties(
                    headers=headers,
                    delivery_mode=PERSISTENT_DELIVERY_MODE,
                    expiration=(
                        None
                        if delay is None
                        else str(ceil(delay * MILLISECONDS_PER_SECOND))
                    ),
                ),
                mandatory=True,
            )
        except (UnroutableError, NackError) as error:
            logger.error(
                f"Broker did not confirm the copy for {queue}, requeueing the "
                f"original message: {error}"
            )
            channel.basic_nack(delivery_tag, requeue=True)
            return
        channel.basic_ack(delivery_tag)

    def _auth_failure_action(
        self,
        error: AuthRequirementDeniedError,
    ) -> RabbitMQAuthFailureAction:
        decision = error.decision
        if decision is None:
            return self._auth_error_action
        return {
            AuthorizationDecisionState.ALLOW: self._auth_error_action,
            AuthorizationDecisionState.CHALLENGE: self._auth_challenge_action,
            AuthorizationDecisionState.DENY: self._auth_deny_action,
            AuthorizationDecisionState.ERROR: self._auth_error_action,
        }[decision.state]

    def _check_if_event_set(self) -> None:
        if self._stop_event.is_set():
            self.channel.stop_consuming()
        self.connection.add_callback_threadsafe(self._check_if_event_set)

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register a handler in the subscription of `subscriber` for `event`.

        Args:
            event: The event type to handle.
            handler: The callback function to handle the event.
            subscriber: Independent subscriber the handler belongs to; None is
                the unnamed subscriber consuming the queue named after the event.
            handler_name: Name unique within the subscription.

        Raises:
            SubscriberExchangeRequiredError: A named subscriber is registered
                while no exchange is configured.
        """
        if subscriber is not None and self.exchange_name is None:
            raise SubscriberExchangeRequiredError(subscriber, event)
        self._subscriptions.register(event, handler, subscriber, handler_name)
        if event not in self._adapters:
            # TypeAdapter is invariant; the registry is keyed by the concrete type.
            self._adapters[event] = cast(TypeAdapter[AbstractEvent], TypeAdapter(event))

    @override
    def initialize(self) -> None:
        """Initialize RabbitMQ connection and declare subscriber queues.

        Declares, for every subscription, the subscriber queue (bound to the
        exchange when one is configured), its dead-letter queue and, in
        delayed retry mode, its wait queue, then starts consuming.
        """
        self.connection = BlockingConnection(
            parameters=URLParameters(self.connection_string)
        )
        self.channel = self.connection.channel()
        self.publish_channel = self.connection.channel()
        self.publish_channel.confirm_delivery()
        if self._retry.mode is RetryMode.BLOCKING:
            self.channel.basic_qos(prefetch_count=BLOCKING_PREFETCH_COUNT)
        if self.exchange_name is not None:
            self.channel.exchange_declare(self.exchange_name)

        for delivery in self._subscriptions:
            queues = self._queues(delivery)
            self.channel.queue_declare(queues.queue, durable=True)
            if self.exchange_name is not None:
                self.channel.queue_bind(
                    queues.queue,
                    self.exchange_name,
                    EventRouting.name_of(delivery.event_type),
                )
            self.channel.queue_declare(queues.dead_letter_queue, durable=True)
            if self._retry.mode is RetryMode.DELAYED:
                self.channel.queue_declare(
                    queues.retry_queue,
                    durable=True,
                    arguments={  # pyrefly: ignore[bad-argument-type] - pika-stubs mistypes queue arguments as DeclareOk; pika takes a dict
                        DEAD_LETTER_EXCHANGE_ARGUMENT: DEFAULT_EXCHANGE_NAME,
                        DEAD_LETTER_ROUTING_KEY_ARGUMENT: queues.queue,
                    },
                )
            self.channel.basic_consume(
                queues.queue,
                partial(self._on_message, delivery, queues),
            )

    @override
    def dispose(self) -> None:
        """Clean up RabbitMQ resources.

        Closes the channel and connection when the service is stopped.
        Messages still waiting for a blocking retry return to their queue.
        """
        self.channel.close()
        self.connection.close()
        return

    @override
    def run(self) -> None:
        """Run the event consumer loop.

        Starts consuming messages from RabbitMQ queues and blocks until
        the stop event is set.
        """
        self.connection.add_callback_threadsafe(self._check_if_event_set)
        self.channel.start_consuming()

    @override
    def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Run the failed handlers of this subscriber's dead letters again.

        Opens a connection of its own, so it may be called from any thread
        while the consumer is running. A dead letter that fails again is held
        until every stored one was taken, then replaced by a copy whose
        metadata lists only the handlers that failed again, so a handler that
        succeeded here is not run by the next redrive. Each dead letter is
        delivered at most once per call.

        Raises:
            SubscriptionNotFoundError: Nothing is registered for the pair.
        """
        delivery = self._subscriptions.get(subscriber, event)
        queues = self._queues(delivery)
        connection = BlockingConnection(
            parameters=URLParameters(self.connection_string)
        )
        try:
            channel = connection.channel()
            publish_channel = connection.channel()
            publish_channel.confirm_delivery()
            channel.queue_declare(queues.dead_letter_queue, durable=True)
            succeeded = 0
            kept: list[tuple[int, bytes, dict[str, str]]] = []
            while limit is None or succeeded + len(kept) < limit:
                method_frame, properties, body = channel.basic_get(
                    queues.dead_letter_queue
                )
                if (
                    method_frame is None
                    or method_frame.delivery_tag is None
                    or properties is None
                    or body is None
                ):
                    # 큐에 더 남은 dead letter가 없다.
                    break
                payload: bytes = body  # pyrefly: ignore[bad-assignment] - pika-stubs types the body as str; pika returns bytes
                still_dead = self._redrive(
                    delivery, self._to_string_headers(properties.headers), payload
                )
                if still_dead is None:
                    channel.basic_ack(method_frame.delivery_tag)
                    succeeded += 1
                    continue
                # 사본을 바로 넣으면 이 호출이 다시 꺼내게 되므로 끝까지 쥐고 있는다.
                kept.append((method_frame.delivery_tag, payload, still_dead))
            for delivery_tag, payload, headers in kept:
                self._forward(
                    channel,
                    publish_channel,
                    delivery_tag,
                    queues.dead_letter_queue,
                    payload,
                    headers,
                    None,
                )
            return RedriveResult(succeeded=succeeded, failed=len(kept))
        finally:
            connection.close()

    def _redrive(
        self, delivery: SubscriptionDelivery, carrier: dict[str, str], body: bytes
    ) -> dict[str, str] | None:
        """Deliver one dead letter to its failed handlers.

        Returns:
            None when every failed handler completed (nothing is left to
            keep); otherwise the headers of the dead letter to keep, with its
            metadata narrowed to the handlers that failed again.
        """
        try:
            dead_letter = DeadLetter.from_headers(carrier)
        except InvalidDeliveryHeaderError as error:
            logger.warning(f"Dead letter has no usable metadata, keeping it: {error}")
            return carrier
        outcome, _ = self._attempt(
            delivery, carrier, body, DeliveryState(pending=dead_letter.pending)
        )
        if isinstance(outcome, DeliveryCompleted):
            return None
        if isinstance(outcome, DeliveryDeadLettered):
            failures = outcome.dead_letter.failures
        elif isinstance(outcome, DeliveryRetry):
            failures = outcome.failures
        else:
            pending = outcome.state.pending
            failures = tuple(
                failure
                for failure in dead_letter.failures
                if pending is None or failure.handler in pending
            )
        return {
            **carrier,
            **dead_letter.model_copy(update={"failures": failures}).to_headers(),
        }


@Pod()
class AsyncRabbitMQEventConsumer(
    IAsyncIntegrationEventConsumer, IAsyncEventRedriver, AbstractAsyncBackgroundService
):
    """Asynchronous RabbitMQ event consumer.

    Runs as an async background service that consumes one durable queue per
    subscriber and delivers each message to that subscriber's asynchronous
    handlers under the delivery contract: failed handlers are retried by
    `RetryPolicy`, and a message the subscriber gives up on moves to the
    subscriber's own dead-letter queue. Uses a robust connection for automatic
    reconnection.

    Attributes:
        connection_string: AMQP connection string.
        exchange_name: Exchange subscriber queues are bound to, if configured.
        connection: Robust RabbitMQ connection for async operations.
        channel: Channel for message consumption.
        publish_channel: Confirm-mode channel for retry and dead-letter copies.
    """

    connection_string: str
    exchange_name: str | None
    connection: AbstractRobustConnection
    channel: AbstractChannel
    publish_channel: AbstractChannel
    _retry: RetryPolicy
    _subscriptions: AsyncEventSubscriptions
    _adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]
    _propagator: ITracePropagator | None
    _auth_challenge_action: RabbitMQAuthFailureAction
    _auth_deny_action: RabbitMQAuthFailureAction
    _auth_error_action: RabbitMQAuthFailureAction

    def __init__(self, config: RabbitMQConnectionConfig) -> None:
        """Initialize the asynchronous RabbitMQ event consumer.

        Args:
            config: RabbitMQ connection configuration.
        """
        self.connection_string = config.connection_string
        self.exchange_name = config.exchange_name
        self._retry = config.retry
        self._subscriptions = AsyncEventSubscriptions(config.retry)
        self._adapters = {}
        self._propagator = None
        self._auth_challenge_action = config.auth_challenge_action
        self._auth_deny_action = config.auth_deny_action
        self._auth_error_action = config.auth_error_action

    def set_propagator(self, propagator: ITracePropagator) -> None:
        """Set the trace propagator for extracting trace context from messages.

        Args:
            propagator: The trace propagator instance.
        """
        self._propagator = propagator

    @staticmethod
    def _to_string_headers(raw: Mapping[str, object] | None) -> dict[str, str]:
        """Convert AMQP headers to a string-valued carrier dict.

        AMQP headers may contain bytes values (RabbitMQ encodes strings as
        bytes). This method decodes bytes and keeps str values, skipping
        other types.

        Args:
            raw: Raw AMQP headers dict, or None.

        Returns:
            A dict with string keys and string values.
        """
        if raw is None or not isinstance(raw, Mapping):
            return {}
        result: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(value, str):
                result[key] = value
            elif isinstance(value, bytes):
                result[key] = value.decode()
        return result

    def _queues(
        self, delivery: AsyncSubscriptionDelivery
    ) -> RabbitMQSubscriptionQueues:
        return RabbitMQSubscriptionQueues.of(
            EventRouting.name_of(delivery.event_type), delivery.subscriber
        )

    async def _on_message(
        self,
        delivery: AsyncSubscriptionDelivery,
        queues: RabbitMQSubscriptionQueues,
        message: AbstractIncomingMessage,
    ) -> None:
        """Deliver one incoming message to the subscriber that owns its queue.

        A blocking retry or a deferral keeps the message unacknowledged and
        waits here; with prefetch 1 the next message of the same queue is not
        delivered until this one is settled.
        """
        if message.consumer_tag is None or message.delivery_tag is None:
            raise InvalidMessageError("Missing consumer tag or delivery tag.")
        carrier = self._to_string_headers(message.headers)
        state: DeliveryState | None = None
        while True:
            try:
                outcome, drop = await self._attempt(
                    delivery, carrier, message.body, state
                )
            except (
                AuthVerificationProviderUnavailableError,
                AuthRequirementProviderUnavailableError,
            ) as error:
                # 인증 기반 장애는 메시지에 대한 판정이 아니므로 확인하지 않고 되돌린다.
                logger.warning(
                    f"Auth is unavailable for {queues.queue}, requeueing the "
                    f"message: {error}"
                )
                await message.nack(requeue=True)
                return
            if isinstance(outcome, DeliveryCompleted):
                if drop:
                    await message.nack(requeue=False)
                    return
                await message.ack()
                return
            if isinstance(outcome, DeliveryDeadLettered):
                await self._forward(
                    self.publish_channel,
                    message,
                    queues.dead_letter_queue,
                    {**carrier, **outcome.dead_letter.to_headers()},
                    None,
                )
                return
            delay = (
                outcome.delay
                if isinstance(outcome, DeliveryRetry)
                else outcome.retry_after
            )
            if self._retry.mode is RetryMode.DELAYED:
                await self._forward(
                    self.publish_channel,
                    message,
                    queues.retry_queue,
                    {**carrier, **outcome.state.to_headers()},
                    delay,
                )
                return
            if await self._stopped_within(delay):
                # 종료 중에는 다시 실행하지 않고 브로커에 되돌린다.
                await message.nack(requeue=True)
                return
            state = outcome.state

    async def _stopped_within(self, seconds: float) -> bool:
        """Wait out a retry delay; report True when the service stops first."""
        try:
            await wait_for(self._stop_event.wait(), timeout=seconds)
        except AsyncTimeoutError:
            return False
        return True

    async def _attempt(
        self,
        delivery: AsyncSubscriptionDelivery,
        carrier: dict[str, str],
        body: bytes,
        state: DeliveryState | None,
    ) -> tuple[DeliveryOutcome, bool]:
        """Deserialize a message and run the pending handlers once.

        Returns:
            The delivery outcome, and whether the auth policy asked to reject
            the message instead of acknowledging it.

        Raises:
            AuthVerificationProviderUnavailableError: Snapshot verification is
                unavailable; the message must stay unacknowledged.
            AuthRequirementProviderUnavailableError: Authorization data is
                unavailable, or the auth policy asked for a requeue.
        """
        if self._propagator is not None:
            parent = self._propagator.extract(carrier)
            ctx = parent.child() if parent is not None else TraceContext.new_root()
            TraceContext.set(ctx)
        token = set_current_rabbitmq_message_headers(carrier)
        auth = RabbitMQAuthSettlement()
        try:
            try:
                current = (
                    DeliveryState.from_headers(carrier) if state is None else state
                )
            except InvalidDeliveryHeaderError as error:
                return self._unprocessable(delivery, DeliveryState(), error), False
            try:
                event = self._adapters[delivery.event_type].validate_json(body)
            except ValidationError as error:
                return self._unprocessable(delivery, current, error), False
            outcome = await delivery.deliver(
                event, current, partial(self._invoke, auth)
            )
            return outcome, auth.drop
        finally:
            reset_current_rabbitmq_message_headers(token)
            if self._propagator is not None:
                TraceContext.clear()

    def _unprocessable(
        self,
        delivery: AsyncSubscriptionDelivery,
        state: DeliveryState,
        error: Exception,
    ) -> DeliveryDeadLettered:
        """Dead-letter a message no retry can turn into a handler call."""
        logger.warning(
            f"Message for {EventRouting.name_of(delivery.event_type)} cannot be "
            f"processed, dead-lettering it: {error}"
        )
        return DeliveryDeadLettered(
            dead_letter=DeadLetter(
                event_name=EventRouting.name_of(delivery.event_type),
                subscriber=delivery.subscriber,
                failures=tuple(
                    HandlerFailure(
                        handler=handler.name,
                        exception_type=type(error).__qualname__,
                        exception_message=str(error),
                        retryable=False,
                    )
                    for handler in delivery.handlers
                    if state.pending is None or handler.name in state.pending
                ),
                attempts=state.attempt,
                failed_at=datetime.now(UTC),
            )
        )

    async def _invoke(
        self,
        auth: RabbitMQAuthSettlement,
        # Any: the delivery engine erases the concrete event type of callbacks.
        handler: RegisteredEventHandler[AsyncEventHandlerCallback[Any]],
        event: AbstractEvent,
    ) -> None:
        """Await a handler and map an auth denial onto the configured action."""
        try:
            await handler.callback(event)
        except AuthRequirementDeniedError as error:
            action = self._auth_failure_action(error)
            if action is RabbitMQAuthFailureAction.NACK_REQUEUE:
                raise RabbitMQAuthRequeueError() from error
            if action is RabbitMQAuthFailureAction.NACK_DROP:
                auth.drop = True
            raise

    async def _forward(
        self,
        publish_channel: AbstractChannel,
        message: AbstractIncomingMessage,
        queue: QueueName,
        headers: dict[str, str],
        delay: float | None,
    ) -> None:
        """Move a message to another queue of the subscriber.

        The original is acknowledged only after the broker confirmed the copy;
        otherwise it is requeued so that it cannot be lost.

        Args:
            publish_channel: Confirm-mode channel the copy is published on.
            message: Original message.
            queue: Retry or dead-letter queue receiving the copy.
            headers: Headers of the copy, including retry or dead-letter state.
            delay: Seconds the copy waits before it expires back into the
                subscriber queue; None stores it without expiration.
        """
        try:
            await publish_channel.default_exchange.publish(
                Message(
                    body=message.body,
                    headers=dict(headers),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    expiration=None if delay is None else timedelta(seconds=delay),
                ),
                routing_key=queue,
            )
        except DeliveryError as error:
            logger.error(
                f"Broker did not confirm the copy for {queue}, requeueing the "
                f"original message: {error}"
            )
            await message.nack(requeue=True)
            return
        await message.ack()

    def _auth_failure_action(
        self,
        error: AuthRequirementDeniedError,
    ) -> RabbitMQAuthFailureAction:
        decision = error.decision
        if decision is None:
            return self._auth_error_action
        return {
            AuthorizationDecisionState.ALLOW: self._auth_error_action,
            AuthorizationDecisionState.CHALLENGE: self._auth_challenge_action,
            AuthorizationDecisionState.DENY: self._auth_deny_action,
            AuthorizationDecisionState.ERROR: self._auth_error_action,
        }[decision.state]

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register an async handler in the subscription of `subscriber` for `event`.

        Args:
            event: The event type to handle.
            handler: The async callback function to handle the event.
            subscriber: Independent subscriber the handler belongs to; None is
                the unnamed subscriber consuming the queue named after the event.
            handler_name: Name unique within the subscription.

        Raises:
            SubscriberExchangeRequiredError: A named subscriber is registered
                while no exchange is configured.
        """
        if subscriber is not None and self.exchange_name is None:
            raise SubscriberExchangeRequiredError(subscriber, event)
        self._subscriptions.register(event, handler, subscriber, handler_name)
        if event not in self._adapters:
            # TypeAdapter is invariant; the registry is keyed by the concrete type.
            self._adapters[event] = cast(TypeAdapter[AbstractEvent], TypeAdapter(event))

    @override
    async def initialize_async(self) -> None:
        """Initialize async RabbitMQ connection and declare subscriber queues.

        Declares, for every subscription, the subscriber queue (bound to the
        exchange when one is configured), its dead-letter queue and, in
        delayed retry mode, its wait queue, then starts consuming.
        """
        self.connection = await connect_robust(self.connection_string)
        self.channel = await self.connection.channel()
        self.publish_channel = await self.connection.channel(on_return_raises=True)
        if self._retry.mode is RetryMode.BLOCKING:
            await self.channel.set_qos(prefetch_count=BLOCKING_PREFETCH_COUNT)
        exchange = (
            await self.channel.declare_exchange(self.exchange_name)
            if self.exchange_name is not None
            else None
        )

        for delivery in self._subscriptions:
            queues = self._queues(delivery)
            queue = await self.channel.declare_queue(queues.queue, durable=True)
            if exchange is not None:
                await queue.bind(exchange, EventRouting.name_of(delivery.event_type))
            await self.channel.declare_queue(queues.dead_letter_queue, durable=True)
            if self._retry.mode is RetryMode.DELAYED:
                await self.channel.declare_queue(
                    queues.retry_queue,
                    durable=True,
                    arguments={
                        DEAD_LETTER_EXCHANGE_ARGUMENT: DEFAULT_EXCHANGE_NAME,
                        DEAD_LETTER_ROUTING_KEY_ARGUMENT: queues.queue,
                    },
                )
            await queue.consume(partial(self._on_message, delivery, queues))

    @override
    async def dispose_async(self) -> None:
        """Clean up async RabbitMQ resources.

        Closes the channel and connection when the service is stopped.
        """
        await self.channel.close()
        await self.connection.close()
        return

    @override
    async def run_async(self) -> None:
        """Run the async event consumer loop.

        Waits for the stop event to be set while consuming messages from
        RabbitMQ queues in the background.
        """
        await self._stop_event.wait()

    @override
    async def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Run the failed handlers of this subscriber's dead letters again.

        Opens a connection of its own. A dead letter that fails again is held
        until every stored one was taken, then replaced by a copy whose
        metadata lists only the handlers that failed again, so a handler that
        succeeded here is not run by the next redrive. Each dead letter is
        delivered at most once per call.

        Raises:
            SubscriptionNotFoundError: Nothing is registered for the pair.
        """
        delivery = self._subscriptions.get(subscriber, event)
        queues = self._queues(delivery)
        async with await connect_robust(self.connection_string) as connection:
            channel = await connection.channel()
            publish_channel = await connection.channel(on_return_raises=True)
            queue = await channel.declare_queue(queues.dead_letter_queue, durable=True)
            succeeded = 0
            kept: list[tuple[AbstractIncomingMessage, dict[str, str]]] = []
            while limit is None or succeeded + len(kept) < limit:
                message = await queue.get(fail=False)
                if message is None:
                    # 큐에 더 남은 dead letter가 없다.
                    break
                still_dead = await self._redrive(
                    delivery, self._to_string_headers(message.headers), message.body
                )
                if still_dead is None:
                    await message.ack()
                    succeeded += 1
                    continue
                # 사본을 바로 넣으면 이 호출이 다시 꺼내게 되므로 끝까지 쥐고 있는다.
                kept.append((message, still_dead))
            for message, headers in kept:
                await self._forward(
                    publish_channel,
                    message,
                    queues.dead_letter_queue,
                    headers,
                    None,
                )
            return RedriveResult(succeeded=succeeded, failed=len(kept))

    async def _redrive(
        self,
        delivery: AsyncSubscriptionDelivery,
        carrier: dict[str, str],
        body: bytes,
    ) -> dict[str, str] | None:
        """Deliver one dead letter to its failed handlers.

        Returns:
            None when every failed handler completed (nothing is left to
            keep); otherwise the headers of the dead letter to keep, with its
            metadata narrowed to the handlers that failed again.
        """
        try:
            dead_letter = DeadLetter.from_headers(carrier)
        except InvalidDeliveryHeaderError as error:
            logger.warning(f"Dead letter has no usable metadata, keeping it: {error}")
            return carrier
        outcome, _ = await self._attempt(
            delivery, carrier, body, DeliveryState(pending=dead_letter.pending)
        )
        if isinstance(outcome, DeliveryCompleted):
            return None
        if isinstance(outcome, DeliveryDeadLettered):
            failures = outcome.dead_letter.failures
        elif isinstance(outcome, DeliveryRetry):
            failures = outcome.failures
        else:
            pending = outcome.state.pending
            failures = tuple(
                failure
                for failure in dead_letter.failures
                if pending is None or failure.handler in pending
            )
        return {
            **carrier,
            **dead_letter.model_copy(update={"failures": failures}).to_headers(),
        }
