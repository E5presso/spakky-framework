"""Spakky Event package - Event-driven architecture support.

This package provides:
- Event publishers and consumers
- Event handler stereotype
- Event-related errors

Usage:
    from spakky.event import IIntegrationEventPublisher, IAsyncIntegrationEventPublisher
    from spakky.event import IIntegrationEventConsumer, IAsyncIntegrationEventConsumer
"""

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
from spakky.event.event_publisher import (
    IAsyncDomainEventPublisher,
    IAsyncIntegrationEventPublisher,
    IDomainEventPublisher,
    IIntegrationEventPublisher,
)

__all__ = [
    # Publishers
    "IAsyncDomainEventPublisher",
    "IDomainEventPublisher",
    "IAsyncIntegrationEventPublisher",
    "IIntegrationEventPublisher",
    # Consumers
    "IAsyncDomainEventConsumer",
    "IDomainEventConsumer",
    "IAsyncIntegrationEventConsumer",
    "IIntegrationEventConsumer",
    # Errors
    "AbstractSpakkyEventError",
    "DuplicateEventHandlerError",
    "InvalidMessageError",
]
