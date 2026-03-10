"""Spakky Event package - Event-driven architecture support."""

from spakky.event.aspects import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.bus import (
    AsyncDirectEventBus,
    DirectEventBus,
)
from spakky.event.error import (
    AbstractSpakkyEventError,
    DuplicateEventHandlerError,
    InvalidMessageError,
)
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
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
from spakky.event.mediator import (
    AsyncEventMediator,
    EventMediator,
)
from spakky.event.post_processor import EventHandlerRegistrationPostProcessor
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
    # Dispatcher Interfaces
    "IAsyncEventDispatcher",
    "IEventDispatcher",
    # Mediator Implementations
    "AsyncEventMediator",
    "EventMediator",
    # Publisher Implementations
    "AsyncEventPublisher",
    "EventPublisher",
    # Bus Implementations
    "AsyncDirectEventBus",
    "DirectEventBus",
    # Post-Processors
    "EventHandlerRegistrationPostProcessor",
    # Aspects
    "AsyncTransactionalEventPublishingAspect",
    "TransactionalEventPublishingAspect",
    # Errors
    "AbstractSpakkyEventError",
    "DuplicateEventHandlerError",
    "InvalidMessageError",
]

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-event")
"""Plugin identifier for the Spakky Event package."""
