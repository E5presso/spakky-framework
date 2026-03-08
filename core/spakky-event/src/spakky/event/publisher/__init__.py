"""Spakky Event Publisher package.

This package provides event publisher implementations with type-based routing.
"""

from spakky.event.publisher.domain_event_publisher import (
    AsyncEventPublisher,
    EventPublisher,
)

__all__ = [
    "AsyncEventPublisher",
    "EventPublisher",
]
