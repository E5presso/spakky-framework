from collections.abc import Sequence
from typing import Protocol

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractDomainEvent


class ICollectableAggregate(Protocol):
    """Structural type for aggregates tracked by collector."""

    @property
    def uid(self) -> IEquatable: ...

    @property
    def events(self) -> Sequence[AbstractDomainEvent]: ...

    def clear_events(self) -> None: ...


@Pod(scope=Pod.Scope.CONTEXT)
class AggregateCollector:
    """Context-scoped collector for tracking aggregates saved in a transaction."""

    _aggregates: list[ICollectableAggregate]

    def __init__(self) -> None:
        self._aggregates = []

    def collect(self, aggregate: ICollectableAggregate) -> None:
        """Track an aggregate that was saved during the transaction.

        This method is called by Repository implementations after saving
        an aggregate to the database. The collector stores a reference
        to track which aggregates were modified.

        Args:
            aggregate: The aggregate to track.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Alice")
            >>> collector.collect(user)
        """
        self._aggregates.append(aggregate)

    def all(self) -> Sequence[ICollectableAggregate]:
        """Get all tracked aggregates.

        Returns a sequence of all aggregates collected during the current
        transaction. This is typically called by aspects after the use case
        logic completes to extract domain events.

        Returns:
            Sequence of tracked aggregates.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Bob")
            >>> collector.collect(user)
            >>> aggregates = collector.get_all()
            >>> len(aggregates)
            1
        """
        return list(self._aggregates)

    def clear(self) -> None:
        """Clear all tracked aggregates.

        This method is called after events have been published or when
        a transaction completes (success or failure) to prepare the
        collector for the next transaction.

        Example:
            >>> collector = AggregateCollector()
            >>> user = User.create(name="Charlie")
            >>> collector.collect(user)
            >>> collector.clear()
            >>> len(collector.get_all())
            0
        """
        self._aggregates.clear()
