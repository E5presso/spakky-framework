"""Spakky Event package - Event-driven architecture support.

This package provides:
- Event publishers and consumers
- Event handler stereotype
- Event-related errors

Usage:
    from spakky.event import IEventPublisher, IAsyncEventPublisher
    from spakky.event import IEventConsumer, IAsyncEventConsumer
"""

from spakky.event.error import (
    AbstractSpakkyEventError,
    DuplicateEventHandlerError,
    InvalidMessageError,
)
from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)
from spakky.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)

__all__ = [
    # Publishers
    "IAsyncEventPublisher",
    "IEventPublisher",
    # Consumers
    "IAsyncEventConsumer",
    "IEventConsumer",
    # Errors
    "AbstractSpakkyEventError",
    "DuplicateEventHandlerError",
    "InvalidMessageError",
]
