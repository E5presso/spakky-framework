"""Domain models for DDD building blocks.

This module provides base classes for domain-driven design:
- AbstractEntity: Entities with identity
- AbstractValueObject: Immutable value objects
- AbstractAggregateRoot: Aggregate roots managing consistency boundaries
- AbstractDomainEvent: Domain events for event sourcing
- AbstractIntegrationEvent: Integration events for cross-boundary communication
"""

from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.entity import AbstractEntity
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from spakky.domain.models.value_object import AbstractValueObject

__all__ = [
    "AbstractAggregateRoot",
    "AbstractDomainEvent",
    "AbstractEntity",
    "AbstractIntegrationEvent",
    "AbstractValueObject",
]
