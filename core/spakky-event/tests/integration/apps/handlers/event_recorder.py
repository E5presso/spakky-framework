"""Event recorder for tracking handler invocations in tests."""

from dataclasses import dataclass, field
from typing import Any

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractDomainEvent


@dataclass
class EventRecord:
    """Record of a single event handler invocation."""

    handler_name: str
    """Name of the handler that was invoked."""

    event: AbstractDomainEvent
    """The event that was handled."""


@Pod(scope=Pod.Scope.CONTEXT)
@dataclass
class EventRecorder:
    """Context-scoped recorder for tracking event handler invocations.

    Use this to verify that events were properly dispatched to handlers
    and to check the order of handler invocations.

    Example:
        >>> recorder = EventRecorder()
        >>> # After running use case that triggers events
        >>> assert len(recorder.records) == 1
        >>> assert recorder.records[0].handler_name == "AsyncOrderEventHandler"
    """

    records: list[EventRecord] = field(default_factory=list)
    """List of event records in invocation order."""

    def record(self, handler_name: str, event: AbstractDomainEvent) -> None:
        """Record an event handler invocation.

        Args:
            handler_name: Name of the handler that was invoked.
            event: The event that was handled.
        """
        self.records.append(EventRecord(handler_name=handler_name, event=event))

    def clear(self) -> None:
        """Clear all recorded events."""
        self.records.clear()

    def count_by_handler(self, handler_name: str) -> int:
        """Count invocations for a specific handler.

        Args:
            handler_name: Name of the handler to count.

        Returns:
            Number of invocations for the handler.
        """
        return len([r for r in self.records if r.handler_name == handler_name])

    def count_by_event_type(self, event_type: type[Any]) -> int:
        """Count invocations for a specific event type.

        Args:
            event_type: Type of event to count.

        Returns:
            Number of invocations for the event type.
        """
        return len([r for r in self.records if isinstance(r.event, event_type)])

    def get_events_by_handler(self, handler_name: str) -> list[AbstractDomainEvent]:
        """Get all events handled by a specific handler.

        Args:
            handler_name: Name of the handler.

        Returns:
            List of events handled by the handler.
        """
        return [r.event for r in self.records if r.handler_name == handler_name]
