"""Spakky Event Aspects package.

This package provides aspects for event-driven architecture:
- TransactionalEventPublishingAspect: Automatic domain event publishing after transactions
- IdempotentAspect: Skip integration events a handler already processed
"""

from spakky.event.aspects.idempotent import AsyncIdempotentAspect, IdempotentAspect
from spakky.event.aspects.transactional_event_publishing import (
    AsyncTransactionalEventPublishingAspect,
    TransactionalEventPublishingAspect,
)

__all__ = [
    "AsyncIdempotentAspect",
    "IdempotentAspect",
    "AsyncTransactionalEventPublishingAspect",
    "TransactionalEventPublishingAspect",
]
