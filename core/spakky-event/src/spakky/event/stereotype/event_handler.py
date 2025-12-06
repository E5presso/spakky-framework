"""EventHandler stereotype and event routing decorators.

This module provides @EventHandler stereotype and @on_event decorator
for organizing event-driven architectures.
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeAlias, TypeVar

from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractDomainEvent

DomainEventT = TypeVar("DomainEventT", bound=AbstractDomainEvent)
"""Type variable for domain event types."""

IEventHandlerMethod: TypeAlias = Callable[[Any, DomainEventT], None | Awaitable[None]]
"""Type alias for event handler callback functions."""


@dataclass
class EventRoute(FunctionAnnotation, Generic[DomainEventT]):
    """Annotation for marking methods as event handlers.

    Associates a method with a specific domain event type.
    """

    event_type: type[DomainEventT]
    """The domain event type this handler processes."""

    def __call__(
        self, obj: IEventHandlerMethod[DomainEventT]
    ) -> IEventHandlerMethod[DomainEventT]:
        """Apply event route annotation to method.

        Args:
            obj: The method to annotate.

        Returns:
            The annotated method.
        """
        return super().__call__(obj)


def on_event(
    event_type: type[DomainEventT],
) -> Callable[
    [IEventHandlerMethod[DomainEventT]],
    IEventHandlerMethod[DomainEventT],
]:
    """Decorator for marking methods as event handlers.

    Args:
        event_type: The domain event type to handle.

    Returns:
        Decorator function that applies EventRoute annotation.

    Example:
        @EventHandler()
        class UserEventHandler:
            @on_event(UserCreatedEvent)
            async def handle_user_created(self, event: UserCreatedEvent) -> None:
                # Handle event
                pass
    """

    def wrapper(
        method: IEventHandlerMethod[DomainEventT],
    ) -> IEventHandlerMethod[DomainEventT]:
        return EventRoute(event_type)(method)

    return wrapper


@dataclass(eq=False)
class EventHandler(Pod):
    """Stereotype for event handler classes.

    EventHandlers contain methods decorated with @on_event that
    process domain events asynchronously.
    """

    ...
