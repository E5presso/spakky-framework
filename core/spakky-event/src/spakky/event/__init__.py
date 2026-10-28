"""Spakky Event package - Event-driven architecture support."""

from spakky.event.aspects import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
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
]

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-event")
"""Plugin identifier for the Spakky Event package."""
