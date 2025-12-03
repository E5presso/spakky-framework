"""Domain event models for event-driven architecture.

This module provides base classes for domain and integration events
in event-driven systems.
"""

from abc import ABC
from copy import deepcopy
from dataclasses import field
from datetime import datetime, timezone
from typing import Self
from uuid import UUID, uuid4

from spakky.core.interfaces.cloneable import ICloneable
from spakky.core.interfaces.comparable import IComparable
from spakky.core.interfaces.equatable import IEquatable
from spakky.core.mutability import immutable


@immutable
class AbstractDomainEvent(IEquatable, IComparable, ICloneable, ABC):
    """Base class for domain events.

    Domain events represent state changes within the domain that other
    parts of the system may be interested in.
    """

    event_id: UUID = field(default_factory=uuid4)
    """Unique identifier for this event."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When the event occurred."""

    @property
    def event_name(self) -> str:
        """Get event type name.

        Returns:
            Class name of the event.
        """
        return type(self).__name__

    def clone(self) -> Self:
        """Create deep copy of this event.

        Returns:
            Cloned event instance.
        """
        return deepcopy(self)

    def __eq__(self, other: object) -> bool:
        """Compare events by id and timestamp.

        Args:
            other: Object to compare with.

        Returns:
            True if same event type, id, and timestamp.
        """
        if not isinstance(other, type(self)):
            return False
        return self.event_id == other.event_id and self.timestamp == other.timestamp

    def __hash__(self) -> int:
        """Compute hash from event id and timestamp.

        Returns:
            XOR of id and timestamp hashes.
        """
        return hash(self.event_id) ^ hash(self.timestamp)

    def __lt__(self, __value: Self) -> bool:
        """Compare events by timestamp (less than).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred before the other.
        """
        return self.timestamp < __value.timestamp

    def __le__(self, __value: Self) -> bool:
        """Compare events by timestamp (less than or equal).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred before or at same time as the other.
        """
        return self.timestamp <= __value.timestamp

    def __gt__(self, __value: Self) -> bool:
        """Compare events by timestamp (greater than).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred after the other.
        """
        return self.timestamp > __value.timestamp

    def __ge__(self, __value: Self) -> bool:
        """Compare events by timestamp (greater than or equal).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred after or at same time as the other.
        """
        return self.timestamp >= __value.timestamp


@immutable
class AbstractIntegrationEvent(AbstractDomainEvent, ABC):
    """Base class for integration events.

    Integration events are published across bounded contexts or services
    to communicate significant domain changes.
    """

    ...
