"""Aggregate root model for domain-driven design.

This module provides AbstractAggregateRoot for representing DDD aggregate roots
that manage domain events and maintain consistency boundaries.
"""

from abc import ABC
from dataclasses import field
from typing import Any, Generic, Sequence, TypeVar

from spakky.core.common.interfaces.equatable import EquatableT
from spakky.core.common.mutability import mutable

from spakky.domain.models.entity import AbstractEntity
from spakky.domain.models.event import AbstractDomainEvent


@mutable
class AbstractAggregateRoot(AbstractEntity[EquatableT], Generic[EquatableT], ABC):
    """Base class for DDD aggregate roots.

    Aggregate roots are entities that serve as entry points to aggregates,
    maintaining consistency boundaries and managing domain events.
    """

    __events: list[AbstractDomainEvent] = field(
        init=False,
        repr=False,
        default_factory=list[AbstractDomainEvent],
    )

    @property
    def events(self) -> Sequence[AbstractDomainEvent]:
        """Get copy of all domain events raised by this aggregate.

        Returns:
            Sequence of domain events.
        """
        return list(self.__events)

    def add_event(self, event: AbstractDomainEvent) -> None:
        """Add a domain event to this aggregate.

        Args:
            event: The domain event to add.
        """
        self.__events.append(event)

    def remove_event(self, event: AbstractDomainEvent) -> None:
        """Remove a domain event from this aggregate.

        Args:
            event: The domain event to remove.
        """
        self.__events.remove(event)

    def clear_events(self) -> None:
        """Clear all domain events from this aggregate."""
        self.__events.clear()


AggregateRootT = TypeVar("AggregateRootT", bound=AbstractAggregateRoot[Any])
"""Type variable for aggregate root types."""
