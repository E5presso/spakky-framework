"""Spakky Event package - Event-driven architecture support.

This package provides:
- Event publishers and consumers
- Event dispatchers (ISP-compliant)
- Event mediators (combines consumer and dispatcher)
- Event handler stereotype
- Event-related errors
- Transactional event publishing aspects

Usage:
    from spakky.event import IIntegrationEventPublisher, IAsyncIntegrationEventPublisher
    from spakky.event import IIntegrationEventConsumer, IAsyncIntegrationEventConsumer
    from spakky.event import AsyncTransactionalEventPublishingAspect
    from spakky.event import DomainEventMediator, AsyncDomainEventMediator
    from spakky.event import DomainEventPublisher, AsyncDomainEventPublisher
"""

from spakky.event.aspects import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)
from spakky.event.error import (
    AbstractSpakkyEventError,
    DuplicateEventHandlerError,
    InvalidMessageError,
)
from spakky.event.event_consumer import (
    IAsyncDomainEventConsumer,
    IAsyncIntegrationEventConsumer,
    IDomainEventConsumer,
    IIntegrationEventConsumer,
)
from spakky.event.event_dispatcher import (
    IAsyncDomainEventDispatcher,
    IAsyncIntegrationEventDispatcher,
    IDomainEventDispatcher,
    IIntegrationEventDispatcher,
)
from spakky.event.event_publisher import (
    IAsyncDomainEventPublisher,
    IAsyncIntegrationEventPublisher,
    IDomainEventPublisher,
    IIntegrationEventPublisher,
)
from spakky.event.mediator import (
    AsyncDomainEventMediator,
    DomainEventMediator,
)
from spakky.event.post_processor import EventHandlerRegistrationPostProcessor
from spakky.event.publisher import (
    AsyncDomainEventPublisher,
    DomainEventPublisher,
)

__all__ = [
    # Publisher Interfaces
    "IAsyncDomainEventPublisher",
    "IDomainEventPublisher",
    "IAsyncIntegrationEventPublisher",
    "IIntegrationEventPublisher",
    # Consumer Interfaces
    "IAsyncDomainEventConsumer",
    "IDomainEventConsumer",
    "IAsyncIntegrationEventConsumer",
    "IIntegrationEventConsumer",
    # Dispatcher Interfaces (ISP)
    "IAsyncDomainEventDispatcher",
    "IDomainEventDispatcher",
    "IAsyncIntegrationEventDispatcher",
    "IIntegrationEventDispatcher",
    # Mediator Implementations
    "AsyncDomainEventMediator",
    "DomainEventMediator",
    # Publisher Implementations
    "AsyncDomainEventPublisher",
    "DomainEventPublisher",
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
