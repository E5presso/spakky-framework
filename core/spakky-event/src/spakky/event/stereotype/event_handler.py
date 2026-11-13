"""EventHandler stereotype and event routing decorators.

This module provides @EventHandler stereotype and @on_event decorator
for organizing event-driven architectures.
"""

from dataclasses import dataclass, field
from inspect import getmembers, isfunction, iscoroutinefunction
from typing import Any
from collections.abc import Awaitable, Callable

from spakky.core.common.annotation import FunctionAnnotation
from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractEvent

from spakky.event.subscription import HandlerName, SubscriberName, SubscriberNames

type EventHandlerMethod[EventT_contra: AbstractEvent] = Callable[
    [Any, EventT_contra], None | Awaitable[None]
]
"""Type alias for event handler callback functions."""


@dataclass
class EventRoute[EventT_contra: AbstractEvent](FunctionAnnotation):
    """Annotation for marking methods as event handlers.

    Associates a method with a specific domain event type.
    """

    event_type: type[EventT_contra]
    """The domain event type this handler processes."""

    name: HandlerName | None = None
    """Explicit handler name; None derives `<Class>.<method>`.

    The name identifies the handler in dead-letter metadata and in the
    idempotency key, so set it explicitly when the method may be renamed.
    """

    def handler_name(self, owner: type, method_name: str) -> HandlerName:
        """Return the name this handler is registered under.

        Args:
            owner: Event handler class declaring the method.
            method_name: Name of the decorated method.
        """
        if self.name is not None:
            return self.name
        return f"{owner.__qualname__}.{method_name}"

    def __call__(
        self, obj: EventHandlerMethod[EventT_contra]
    ) -> EventHandlerMethod[EventT_contra]:
        """Apply event route annotation to method.

        Args:
            obj: The method to annotate.

        Returns:
            The annotated method.
        """
        return super().__call__(obj)


def on_event[EventT_contra: AbstractEvent](
    event_type: type[EventT_contra],
    *,
    name: HandlerName | None = None,
) -> Callable[
    [EventHandlerMethod[EventT_contra]],
    EventHandlerMethod[EventT_contra],
]:
    """Decorator for marking methods as event handlers.

    Args:
        event_type: The domain event type to handle.
        name: Explicit handler name; None derives `<Class>.<method>`.

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
        method: EventHandlerMethod[EventT_contra],
    ) -> EventHandlerMethod[EventT_contra]:
        return EventRoute(event_type, name)(method)

    return wrapper


@dataclass(frozen=True, slots=True)
class DeclaredEventRoute:
    """One `@on_event` method as declared on an event handler class."""

    method_name: str
    """Attribute name to look the bound method up on a handler instance."""

    route: EventRoute[AbstractEvent]
    asynchronous: bool
    handler_name: HandlerName


@dataclass(eq=False)
class EventHandler(Pod):
    """Stereotype for event handler classes.

    EventHandlers contain methods decorated with @on_event that
    process domain events asynchronously.

    Example:
        @EventHandler(subscriber="billing")
        class BillingHandler:
            @on_event(OrderPlaced)
            async def charge(self, event: OrderPlaced) -> None: ...
    """

    subscriber: SubscriberName | None = field(kw_only=True, default=None)
    """Independent subscriber the integration handlers of this class belong to.

    Each subscriber reads an integration event stream on its own: it has its
    own consume position, retries and dead-letter destination. None keeps the
    handlers on the unnamed subscriber of the consumer. Domain events are
    dispatched in process and ignore this value.
    """

    def __post_init__(self) -> None:
        """Reject subscriber names that cannot become broker resource names."""
        SubscriberNames.validate(self.subscriber)

    def routes(self) -> list[DeclaredEventRoute]:
        """List the `@on_event` methods declared on the handler class.

        Routes are read from the class, not from an instance: an instance may be
        an AOP proxy whose attributes are plain callables, and scanning it for
        bound methods would silently miss every advised handler.
        """
        declared: list[DeclaredEventRoute] = []
        for method_name, function in getmembers(self.type_, isfunction):
            route: EventRoute[AbstractEvent] | None = EventRoute[
                AbstractEvent
            ].get_or_none(function)
            if route is None:
                continue
            declared.append(
                DeclaredEventRoute(
                    method_name=method_name,
                    route=route,
                    asynchronous=iscoroutinefunction(function),
                    handler_name=route.handler_name(self.type_, method_name),
                )
            )
        return declared
