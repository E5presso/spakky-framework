"""Aggregate root model for domain-driven design.

This module provides AbstractAggregateRoot for representing DDD aggregate roots
that manage domain events and maintain consistency boundaries.
"""

from abc import ABC
from copy import deepcopy
from dataclasses import field
from typing import Any, Generic, Sequence, TypeVar

from spakky.core.interfaces.equatable import EquatableT
from spakky.core.mutability import mutable
from spakky.domain.models.entity import AbstractEntity
from spakky.domain.models.event import AbstractIntegrationEvent


@mutable
class AbstractAggregateRoot(AbstractEntity[EquatableT], Generic[EquatableT], ABC):
    """Base class for DDD aggregate roots.

    Aggregate roots are entities that serve as entry points to aggregates,
    maintaining consistency boundaries and managing domain events.
    """

    __events: list[AbstractIntegrationEvent] = field(
        init=False, repr=False, default_factory=list[AbstractIntegrationEvent]
    )

    @property
    def events(self) -> Sequence[AbstractIntegrationEvent]:
        """Get copy of all domain events raised by this aggregate.

        Returns:
            Sequence of integration events.
        """
        return deepcopy(self.__events)

    def add_event(self, event: AbstractIntegrationEvent) -> None:
        """Add a domain event to this aggregate.

        Args:
            event: The integration event to add.
        """
        self.__events.append(event)

    def remove_event(self, event: AbstractIntegrationEvent) -> None:
        """Remove a domain event from this aggregate.

        Args:
            event: The integration event to remove.
        """
        self.__events.remove(event)

    def clear_events(self) -> None:
        """Clear all domain events from this aggregate."""
        self.__events.clear()


AggregateRootT = TypeVar("AggregateRootT", bound=AbstractAggregateRoot[Any])
"""Type variable for aggregate root types."""
