"""Spakky Domain package - DDD building blocks and CQRS patterns.

This package provides:
- Domain models (Entity, ValueObject, AggregateRoot, Events)
- CQRS application layer (Command, Query)
- Domain errors and validation

Usage:
    from spakky.domain import AbstractEntity, AbstractValueObject
    from spakky.domain import AbstractCommand, ICommandUseCase
"""

# Models
# Application layer (CQRS)
from spakky.domain.application.command import (
    AbstractCommand,
    ICommandUseCase,
)
from spakky.domain.application.query import (
    AbstractQuery,
    IQueryUseCase,
)

# Errors
from spakky.domain.error import (
    AbstractDomainValidationError,
    AbstractSpakkyDomainError,
)
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from spakky.domain.models.entity import AbstractEntity
from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent
from spakky.domain.models.value_object import AbstractValueObject

__all__ = [
    # Models
    "AbstractAggregateRoot",
    "AbstractDomainEvent",
    "AbstractEntity",
    "AbstractIntegrationEvent",
    "AbstractValueObject",
    # CQRS
    "AbstractCommand",
    "AbstractQuery",
    "ICommandUseCase",
    "IQueryUseCase",
    # Errors
    "AbstractDomainValidationError",
    "AbstractSpakkyDomainError",
]
