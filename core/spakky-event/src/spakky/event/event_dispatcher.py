"""Event dispatcher interfaces for dispatching domain and integration events.

This module provides dispatcher interfaces that follow ISP (Interface Segregation Principle).
Dispatchers are responsible for delivering events to registered handlers, while Consumers
are responsible for handler registration. These interfaces are combined in Mediator
implementations.

Usage:
    from spakky.event.event_dispatcher import IAsyncDomainEventDispatcher

    class MyMediator(IAsyncDomainEventConsumer, IAsyncDomainEventDispatcher):
        async def dispatch(self, event: AbstractDomainEvent) -> None:
            # Dispatch to registered handlers
            ...
"""

from abc import ABC, abstractmethod

from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent


class IDomainEventDispatcher(ABC):
    """Interface for synchronously dispatching domain events to handlers.

    This interface is separated from IDomainEventConsumer following ISP.
    Implementations should dispatch events to all registered handlers for that event type.
    """

    @abstractmethod
    def dispatch(self, event: AbstractDomainEvent) -> None:
        """Dispatch a domain event to all registered handlers.

        Args:
            event: The domain event to dispatch.
        """
        ...


class IAsyncDomainEventDispatcher(ABC):
    """Interface for asynchronously dispatching domain events to handlers.

    This interface is separated from IAsyncDomainEventConsumer following ISP.
    Implementations should dispatch events to all registered handlers for that event type.
    """

    @abstractmethod
    async def dispatch(self, event: AbstractDomainEvent) -> None:
        """Dispatch a domain event to all registered handlers asynchronously.

        Args:
            event: The domain event to dispatch.
        """
        ...


class IIntegrationEventDispatcher(ABC):
    """Interface for synchronously dispatching integration events to handlers.

    This interface is separated from IIntegrationEventConsumer following ISP.
    """

    @abstractmethod
    def dispatch(self, event: AbstractIntegrationEvent) -> None:
        """Dispatch an integration event to all registered handlers.

        Args:
            event: The integration event to dispatch.
        """
        ...


class IAsyncIntegrationEventDispatcher(ABC):
    """Interface for asynchronously dispatching integration events to handlers.

    This interface is separated from IAsyncIntegrationEventConsumer following ISP.
    """

    @abstractmethod
    async def dispatch(self, event: AbstractIntegrationEvent) -> None:
        """Dispatch an integration event to all registered handlers asynchronously.

        Args:
            event: The integration event to dispatch.
        """
        ...
