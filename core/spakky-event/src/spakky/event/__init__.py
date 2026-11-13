"""Spakky Event package - Event-driven architecture support."""

from spakky.event.aspects import (
    AsyncIdempotentAspect,
    AsyncTransactionalEventPublishingAspect,
    IdempotentAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.delivery import (
    DeadLetter,
    DeadLetterHeader,
    DeliveryHeader,
    DeliveryState,
    EventDeliveryContext,
    HandlerFailure,
    RetryMode,
    RetryPolicy,
)
from spakky.event.idempotency import (
    IAsyncProcessedEventStore,
    Idempotent,
    IProcessedEventStore,
    ProcessedEventKey,
    ProcessedEventStoreUnavailableError,
    idempotent,
)
from spakky.event.redrive import IAsyncEventRedriver, IEventRedriver, RedriveResult
from spakky.event.subscription import (
    DuplicateEventHandlerNameError,
    InvalidSubscriberNameError,
    MixedSubscriptionModeError,
)
from spakky.event.bus import (
    AsyncDirectEventBus,
    DirectEventBus,
)
from spakky.event.auth_propagation import AuthContextSnapshotHeaderInjector
from spakky.event.error import (
    AbstractSpakkyEventError,
    AuthSnapshotPropagationContextUnavailableError,
    AuthSnapshotPropagationSignerUnavailableError,
    EventDeliveryRejectedError,
    EventTransportNotRunningError,
    InvalidMessageError,
    EventDeferredError,
    InvalidEventDeferralError,
    DomainEventDispatcherUnavailableError,
    EventHandlerProviderUnavailableError,
    AbstractNonRetryableEventError,
    EventDeliveryContextUnavailableError,
    InvalidDeliveryHeaderError,
    SubscriptionNotFoundError,
)
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
    IDomainEventConsumer,
    IAsyncDomainEventConsumer,
    IIntegrationEventConsumer,
    IAsyncIntegrationEventConsumer,
)
from spakky.event.event_dispatcher import (
    IAsyncEventDispatcher,
    IEventDispatcher,
)
from spakky.event.event_publisher import (
    IAsyncEventBus,
    IAsyncEventPublisher,
    IAsyncEventTransport,
    IEventBus,
    IEventPublisher,
    IEventTransport,
)
from spakky.event.publisher import (
    AsyncEventPublisher,
    EventPublisher,
)

__all__ = [
    # Publisher Interfaces
    "IAsyncEventPublisher",
    "IEventPublisher",
    # Bus Interfaces
    "IAsyncEventBus",
    "IEventBus",
    # Transport Interfaces
    "IAsyncEventTransport",
    "IEventTransport",
    # Consumer Interfaces
    "IAsyncEventConsumer",
    "IEventConsumer",
    "IDomainEventConsumer",
    "IAsyncDomainEventConsumer",
    "IIntegrationEventConsumer",
    "IAsyncIntegrationEventConsumer",
    # Dispatcher Interfaces
    "IAsyncEventDispatcher",
    "IEventDispatcher",
    # Publisher Implementations
    "AsyncEventPublisher",
    "EventPublisher",
    # Bus Implementations
    "AuthContextSnapshotHeaderInjector",
    "AsyncDirectEventBus",
    "DirectEventBus",
    # Aspects
    "AsyncTransactionalEventPublishingAspect",
    "TransactionalEventPublishingAspect",
    "AsyncIdempotentAspect",
    "IdempotentAspect",
    # Delivery contract
    "RetryMode",
    "RetryPolicy",
    "DeliveryHeader",
    "DeliveryState",
    "DeadLetter",
    "DeadLetterHeader",
    "HandlerFailure",
    "EventDeliveryContext",
    "IEventRedriver",
    "IAsyncEventRedriver",
    "RedriveResult",
    # Idempotent consumption
    "Idempotent",
    "idempotent",
    "ProcessedEventKey",
    "IProcessedEventStore",
    "IAsyncProcessedEventStore",
    # Errors
    "AbstractSpakkyEventError",
    "AuthSnapshotPropagationContextUnavailableError",
    "AuthSnapshotPropagationSignerUnavailableError",
    "EventDeliveryRejectedError",
    "EventTransportNotRunningError",
    "InvalidMessageError",
    "EventDeferredError",
    "InvalidEventDeferralError",
    "DomainEventDispatcherUnavailableError",
    "EventHandlerProviderUnavailableError",
    "AbstractNonRetryableEventError",
    "EventDeliveryContextUnavailableError",
    "InvalidDeliveryHeaderError",
    "SubscriptionNotFoundError",
    "ProcessedEventStoreUnavailableError",
    "DuplicateEventHandlerNameError",
    "InvalidSubscriberNameError",
    "MixedSubscriptionModeError",
]

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-event")
"""Plugin identifier for the Spakky Event package."""
