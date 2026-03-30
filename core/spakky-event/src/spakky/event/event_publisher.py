"""Event publishing and transport interfaces.

Provides publisher, bus, and transport abstractions for event routing:
- IEventPublisher: Routes events by type (domain vs integration).
- IEventBus: Serializes and sends integration events via transport.
- IEventTransport: Low-level transport for serialized event payloads.
"""

from abc import ABC, abstractmethod

from spakky.domain.models.event import AbstractEvent, AbstractIntegrationEvent


class IEventPublisher(ABC):
    """Publishes events by routing to dispatcher or bus based on event type."""

    @abstractmethod
    def publish(self, event: AbstractEvent) -> None:
        """Publish an event (domain → dispatcher, integration → bus)."""
        ...


class IAsyncEventPublisher(ABC):
    """Async counterpart of IEventPublisher."""

    @abstractmethod
    async def publish(self, event: AbstractEvent) -> None:
        """Publish an event asynchronously."""
        ...


class IEventBus(ABC):
    """Synchronous event bus for sending integration events."""

    @abstractmethod
    def send(self, event: AbstractIntegrationEvent) -> None:
        """Serialize and send an integration event via transport."""
        ...


class IAsyncEventBus(ABC):
    """Asynchronous event bus for sending integration events."""

    @abstractmethod
    async def send(self, event: AbstractIntegrationEvent) -> None:
        """Serialize and send an integration event via transport."""
        ...


class IEventTransport(ABC):
    """Low-level synchronous transport for pre-serialized event payloads."""

    @abstractmethod
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        """Send a serialized event payload to the message broker."""
        ...


class IAsyncEventTransport(ABC):
    """Low-level asynchronous transport for pre-serialized event payloads."""

    @abstractmethod
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        """Send a serialized event payload to the message broker."""
        ...
