"""Consumers that deliver in-memory broker messages to registered handlers."""

from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import sleep as async_sleep
from asyncio import wait_for
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic, sleep
from typing import cast, override

from pydantic import TypeAdapter, ValidationError
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
    DeliveryDeferred,
    DeliveryOutcome,
    DeliveryRetry,
    DeliveryState,
    EventRouting,
    EventSubscriptions,
    HandlerFailure,
    RetryMode,
    SubscriptionDelivery,
)
from spakky.event.event_consumer import (
    AsyncEventHandlerCallback,
    EventHandlerCallback,
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.memory.broker import (
    InMemoryDeadLetter,
    InMemoryEventBroker,
    InMemoryMessage,
    SubscriptionKey,
)
from spakky.event.memory.config import InMemoryEventConfig
from spakky.event.redrive import IAsyncEventRedriver, IEventRedriver, RedriveResult
from spakky.event.subscription import HandlerName, SubscriberName


class InMemorySettlement:
    """Applies a delivery outcome to the in-memory broker."""

    @staticmethod
    def undeserializable(
        message: InMemoryMessage,
        subscriber: SubscriberName | None,
        handlers: list[HandlerName],
        error: ValidationError,
    ) -> DeliveryDeadLettered:
        """Dead-letter a payload no retry can turn into the event type."""
        return DeliveryDeadLettered(
            dead_letter=DeadLetter(
                event_name=message.event_name,
                subscriber=subscriber,
                failures=tuple(
                    HandlerFailure(
                        handler=handler,
                        exception_type=type(error).__qualname__,
                        exception_message=str(error),
                        retryable=False,
                    )
                    for handler in handlers
                ),
                attempts=message.state.attempt,
                failed_at=datetime.now(UTC),
            )
        )

    @staticmethod
    def apply(
        broker: InMemoryEventBroker,
        key: SubscriptionKey,
        message: InMemoryMessage,
        outcome: DeliveryOutcome,
        mode: RetryMode,
    ) -> None:
        """Requeue, dead-letter or drop the message as the outcome requires."""
        match outcome:
            case DeliveryCompleted():
                return
            case DeliveryRetry(state=state, delay=delay):
                retry = message.model_copy(
                    update={"state": state, "not_before": monotonic() + delay}
                )
                if mode is RetryMode.BLOCKING:
                    broker.requeue_front(key, retry)
                else:
                    broker.requeue_back(key, retry)
            case DeliveryDeferred(state=state, retry_after=retry_after):
                broker.requeue_front(
                    key,
                    message.model_copy(
                        update={
                            "state": state,
                            "not_before": monotonic() + retry_after,
                        }
                    ),
                )
            case DeliveryDeadLettered(  # pragma: no branch - exhaustive DeliveryOutcome
                dead_letter=dead_letter
            ):
                broker.add_dead_letter(
                    key, InMemoryDeadLetter(message=message, dead_letter=dead_letter)
                )


@Pod()
class InMemoryEventConsumer(
    IIntegrationEventConsumer, IEventRedriver, AbstractBackgroundService
):
    """Delivers in-memory messages to sync handlers under the delivery contract."""

    _broker: InMemoryEventBroker
    _config: InMemoryEventConfig
    _subscriptions: EventSubscriptions
    _adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]

    def __init__(
        self, broker: InMemoryEventBroker, config: InMemoryEventConfig
    ) -> None:
        super().__init__()
        self._broker = broker
        self._config = config
        self._subscriptions = EventSubscriptions(config.retry)
        self._adapters = {}
        broker.attach(self.drain)

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register a handler and bind its subscriber queue to the event."""
        delivery = self._subscriptions.register(
            event, handler, subscriber, handler_name
        )
        if event not in self._adapters:
            # TypeAdapter is invariant; the registry is keyed by the concrete type.
            self._adapters[event] = cast(TypeAdapter[AbstractEvent], TypeAdapter(event))
        self._broker.bind(self._key(delivery))

    def drain(self) -> int:
        """Deliver every queued message, waiting out retry delays.

        Returns:
            Number of deliveries made, retries included.
        """
        return self._drain(self._sleep_through)

    @override
    def initialize(self) -> None:
        """Nothing to open; queues are bound at registration."""
        return

    @override
    def run(self) -> None:
        """Deliver messages as they arrive until the service is stopped."""
        while not self._stop_event.is_set():
            self._drain(self._stop_event.wait)
            self._stop_event.wait(self._config.poll_interval)

    @override
    def dispose(self) -> None:
        """Nothing to close; queued messages stay inspectable on the broker."""
        return

    @override
    def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Run the failed handlers of this subscriber's dead letters again."""
        delivery = self._subscriptions.get(subscriber, event)
        key = self._key(delivery)
        succeeded = 0
        failed = 0
        for entry in self._broker.take_dead_letters(key, limit):
            outcome = self._deliver(
                delivery,
                entry.message.model_copy(
                    update={
                        "state": DeliveryState(pending=entry.dead_letter.pending),
                        "not_before": 0.0,
                    }
                ),
            )
            if isinstance(outcome, DeliveryCompleted):
                succeeded += 1
                continue
            failed += 1
            self._broker.add_dead_letter(key, entry)
        return RedriveResult(succeeded=succeeded, failed=failed)

    def _key(self, delivery: SubscriptionDelivery) -> SubscriptionKey:
        return (EventRouting.name_of(delivery.event_type), delivery.subscriber)

    def _sleep_through(self, seconds: float) -> bool:
        sleep(seconds)
        return False

    def _drain(self, wait: Callable[[float], bool]) -> int:
        """Deliver until the queues are empty or `wait` reports a stop request."""
        head_only = self._config.retry.mode is RetryMode.BLOCKING
        delivered = 0
        while True:
            progressed = False
            for delivery in self._subscriptions:
                key = self._key(delivery)
                message = self._broker.take(key, monotonic(), head_only)
                if message is None:
                    continue
                try:
                    outcome = self._deliver(delivery, message)
                except BaseException:
                    # 판정 없이 끝난 전달은 메시지를 잃지 않도록 제자리에 되돌린다.
                    self._broker.requeue_front(key, message)
                    raise
                finally:
                    self._broker.done()
                InMemorySettlement.apply(
                    self._broker, key, message, outcome, self._config.retry.mode
                )
                delivered += 1
                progressed = True
            if progressed:
                continue
            due_in = self._broker.next_due_in(
                [self._key(delivery) for delivery in self._subscriptions],
                monotonic(),
                head_only,
            )
            if due_in is None or wait(due_in):
                return delivered

    def _deliver(
        self, delivery: SubscriptionDelivery, message: InMemoryMessage
    ) -> DeliveryOutcome:
        try:
            event = self._adapters[delivery.event_type].validate_json(message.payload)
        except ValidationError as error:
            return InMemorySettlement.undeserializable(
                message,
                delivery.subscriber,
                [handler.name for handler in delivery.handlers],
                error,
            )
        return delivery.deliver(event, message.state)


@Pod()
class AsyncInMemoryEventConsumer(
    IAsyncIntegrationEventConsumer, IAsyncEventRedriver, AbstractAsyncBackgroundService
):
    """Delivers in-memory messages to async handlers under the delivery contract."""

    _broker: InMemoryEventBroker
    _config: InMemoryEventConfig
    _subscriptions: AsyncEventSubscriptions
    _adapters: dict[type[AbstractEvent], TypeAdapter[AbstractEvent]]

    def __init__(
        self, broker: InMemoryEventBroker, config: InMemoryEventConfig
    ) -> None:
        super().__init__()
        self._broker = broker
        self._config = config
        self._subscriptions = AsyncEventSubscriptions(config.retry)
        self._adapters = {}
        broker.attach_async(self.drain_async)

    @override
    def register[EventT_contra: AbstractEvent](
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
        *,
        subscriber: SubscriberName | None = None,
        handler_name: HandlerName | None = None,
    ) -> None:
        """Register an async handler and bind its subscriber queue to the event."""
        delivery = self._subscriptions.register(
            event, handler, subscriber, handler_name
        )
        if event not in self._adapters:
            # TypeAdapter is invariant; the registry is keyed by the concrete type.
            self._adapters[event] = cast(TypeAdapter[AbstractEvent], TypeAdapter(event))
        self._broker.bind(self._key(delivery))

    async def drain_async(self) -> int:
        """Deliver every queued message, waiting out retry delays.

        Returns:
            Number of deliveries made, retries included.
        """
        return await self._drain_async(self._sleep_through_async)

    @override
    async def initialize_async(self) -> None:
        """Nothing to open; queues are bound at registration."""
        return

    @override
    async def run_async(self) -> None:
        """Deliver messages as they arrive until the service is stopped."""
        while not self._stop_event.is_set():
            await self._drain_async(self._wait_for_stop_async)
            await self._wait_for_stop_async(self._config.poll_interval)

    @override
    async def dispose_async(self) -> None:
        """Nothing to close; queued messages stay inspectable on the broker."""
        return

    @override
    async def redrive(
        self,
        event: type[AbstractIntegrationEvent],
        *,
        subscriber: SubscriberName | None = None,
        limit: int | None = None,
    ) -> RedriveResult:
        """Run the failed handlers of this subscriber's dead letters again."""
        delivery = self._subscriptions.get(subscriber, event)
        key = self._key(delivery)
        succeeded = 0
        failed = 0
        for entry in self._broker.take_dead_letters(key, limit):
            outcome = await self._deliver_async(
                delivery,
                entry.message.model_copy(
                    update={
                        "state": DeliveryState(pending=entry.dead_letter.pending),
                        "not_before": 0.0,
                    }
                ),
            )
            if isinstance(outcome, DeliveryCompleted):
                succeeded += 1
                continue
            failed += 1
            self._broker.add_dead_letter(key, entry)
        return RedriveResult(succeeded=succeeded, failed=failed)

    def _key(self, delivery: AsyncSubscriptionDelivery) -> SubscriptionKey:
        return (EventRouting.name_of(delivery.event_type), delivery.subscriber)

    async def _sleep_through_async(self, seconds: float) -> bool:
        await async_sleep(seconds)
        return False

    async def _wait_for_stop_async(self, seconds: float) -> bool:
        try:
            await wait_for(self._stop_event.wait(), timeout=seconds)
        except AsyncTimeoutError:
            return False
        return True

    async def _drain_async(self, wait: Callable[[float], Awaitable[bool]]) -> int:
        """Deliver until the queues are empty or `wait` reports a stop request."""
        head_only = self._config.retry.mode is RetryMode.BLOCKING
        delivered = 0
        while True:
            progressed = False
            for delivery in self._subscriptions:
                key = self._key(delivery)
                message = self._broker.take(key, monotonic(), head_only)
                if message is None:
                    continue
                try:
                    outcome = await self._deliver_async(delivery, message)
                except BaseException:
                    # 판정 없이 끝난 전달은 메시지를 잃지 않도록 제자리에 되돌린다.
                    self._broker.requeue_front(key, message)
                    raise
                finally:
                    self._broker.done()
                InMemorySettlement.apply(
                    self._broker, key, message, outcome, self._config.retry.mode
                )
                delivered += 1
                progressed = True
            if progressed:
                continue
            due_in = self._broker.next_due_in(
                [self._key(delivery) for delivery in self._subscriptions],
                monotonic(),
                head_only,
            )
            if due_in is None or await wait(due_in):
                return delivered

    async def _deliver_async(
        self, delivery: AsyncSubscriptionDelivery, message: InMemoryMessage
    ) -> DeliveryOutcome:
        try:
            event = self._adapters[delivery.event_type].validate_json(message.payload)
        except ValidationError as error:
            return InMemorySettlement.undeserializable(
                message,
                delivery.subscriber,
                [handler.name for handler in delivery.handlers],
                error,
            )
        return await delivery.deliver(event, message.state)
