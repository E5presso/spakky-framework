"""Domain event publisher implementations.

This module provides in-process domain event publisher implementations that
delegate to a dispatcher for event delivery.

Usage:
    from spakky.event.publisher import AsyncDomainEventPublisher

    publisher = AsyncDomainEventPublisher(dispatcher)
    await publisher.publish(UserCreatedEvent(user_id="123"))
"""

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractDomainEvent

from spakky.event.event_dispatcher import (
    IAsyncDomainEventDispatcher,
    IDomainEventDispatcher,
)
from spakky.event.event_publisher import (
    IAsyncDomainEventPublisher,
    IDomainEventPublisher,
)


@Pod()
class DomainEventPublisher(IDomainEventPublisher):
    """In-process synchronous domain event publisher.

    Delegates event publishing to a dispatcher which delivers events to
    all registered handlers. This separation allows publishers to be
    unaware of handler registration details.

    Attributes:
        _dispatcher: The dispatcher responsible for event delivery.
    """

    _dispatcher: IDomainEventDispatcher

    def __init__(self, dispatcher: IDomainEventDispatcher) -> None:
        """Initialize publisher with a dispatcher.

        Args:
            dispatcher: The dispatcher to delegate event delivery to.
        """
        self._dispatcher = dispatcher

    def publish(self, event: AbstractDomainEvent) -> None:
        """Publish a domain event to all registered handlers.

        Args:
            event: The domain event to publish.
        """
        self._dispatcher.dispatch(event)


@Pod()
class AsyncDomainEventPublisher(IAsyncDomainEventPublisher):
    """In-process asynchronous domain event publisher.

    Delegates event publishing to an async dispatcher which delivers events
    to all registered handlers. This separation allows publishers to be
    unaware of handler registration details.

    Attributes:
        _dispatcher: The async dispatcher responsible for event delivery.
    """

    _dispatcher: IAsyncDomainEventDispatcher

    def __init__(self, dispatcher: IAsyncDomainEventDispatcher) -> None:
        """Initialize publisher with an async dispatcher.

        Args:
            dispatcher: The async dispatcher to delegate event delivery to.
        """
        self._dispatcher = dispatcher

    async def publish(self, event: AbstractDomainEvent) -> None:
        """Publish a domain event to all registered handlers asynchronously.

        Args:
            event: The domain event to publish.
        """
        await self._dispatcher.dispatch(event)
