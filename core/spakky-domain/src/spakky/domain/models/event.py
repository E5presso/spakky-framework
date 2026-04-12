"""Domain event models for event-driven architecture.

This module provides base classes for domain and integration events
in event-driven systems.
"""

import sys
from abc import ABC
from dataclasses import field
from datetime import datetime, timezone
from typing import Self
from uuid import UUID, uuid4

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from spakky.core.common.interfaces.cloneable import ICloneable
from spakky.core.common.interfaces.comparable import IComparable
from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import immutable

from spakky.domain.models.base import AbstractDomainModel


@immutable
class AbstractEvent(AbstractDomainModel, IEquatable, IComparable, ICloneable, ABC):
    """Base class for domain events."""

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
        """Create copy of this event.

        Returns:
            Cloned event instance.
        """
        return self

    @override
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

    @override
    def __hash__(self) -> int:
        """Compute hash from event id and timestamp.

        Returns:
            Hash of tuple containing event id and timestamp.
        """
        return hash((self.event_id, self.timestamp))

    @override
    def __lt__(self, __value: Self) -> bool:
        """Compare events by timestamp (less than).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred before the other.
        """
        return self.timestamp < __value.timestamp

    @override
    def __le__(self, __value: Self) -> bool:
        """Compare events by timestamp (less than or equal).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred before or at same time as the other.
        """
        return self.timestamp <= __value.timestamp

    @override
    def __gt__(self, __value: Self) -> bool:
        """Compare events by timestamp (greater than).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred after the other.
        """
        return self.timestamp > __value.timestamp

    @override
    def __ge__(self, __value: Self) -> bool:
        """Compare events by timestamp (greater than or equal).

        Args:
            __value: Event to compare with.

        Returns:
            True if this event occurred after or at same time as the other.
        """
        return self.timestamp >= __value.timestamp


@immutable
class AbstractDomainEvent(AbstractEvent, ABC):
    """Base class for domain events.

    Domain events represent state changes within the domain that other
    parts of the system may be interested in.
    """

    ...


@immutable
class AbstractIntegrationEvent(AbstractEvent, ABC):
    """Base class for integration events.

    Integration events are published across bounded contexts or services
    to communicate significant domain changes.
    """

    ...
