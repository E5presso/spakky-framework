"""Event consumer interfaces for registering event handlers."""

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeAlias, TypeVar

from spakky.domain.models.event import AbstractEvent

EventT_contra = TypeVar("EventT_contra", bound=AbstractEvent, contravariant=True)
EventHandlerCallback: TypeAlias = Callable[[EventT_contra], None]
"""Synchronous event handler callback type."""
AsyncEventHandlerCallback: TypeAlias = Callable[[EventT_contra], Awaitable[None]]
"""Asynchronous event handler callback type."""


class IEventConsumer(ABC):
    """Synchronous event consumer interface for registering event handlers."""

    @abstractmethod
    def register(
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
    ) -> None:
        """Register a handler callback for the given event type."""
        ...


class IAsyncEventConsumer(ABC):
    """Asynchronous event consumer interface for registering event handlers."""

    @abstractmethod
    def register(
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
    ) -> None:
        """Register an async handler callback for the given event type."""
        ...
