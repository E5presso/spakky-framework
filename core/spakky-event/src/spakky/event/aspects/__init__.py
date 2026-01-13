"""Spakky Event Aspects package.

This package provides aspects for event-driven architecture:
- TransactionalEventPublishingAspect: Automatic domain event publishing after transactions
"""

from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)

__all__ = [
    "AsyncTransactionalEventPublishingAspect",
    "TransactionalEventPublishingAspect",
]
