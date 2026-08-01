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
    """Low-level synchronous transport for pre-serialized event payloads.

    The caller owns the publish batch boundary: hand one or more payloads to
    send() and call flush() once at the end of the batch. Transports may buffer
    payloads until flush() so that broker round trips are batched.
    """

    @abstractmethod
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Hand a serialized event payload to the broker client for delivery.

        A permanent rejection attributable to this record must be reported as
        `EventDeliveryRejectedError`. A connection, timeout, queue, or other
        transport-wide failure keeps the client exception's original type so a
        caller does not spend this record's retry budget.

        Args:
            event_name: Destination topic / routing key.
            payload: Pre-serialized event bytes.
            headers: Metadata headers for trace and auth propagation.
            partition_key: Key pinning the payload to one broker partition.
                None spreads payloads round-robin.

        Raises:
            EventDeliveryRejectedError: When the transport permanently rejects
                this specific record.
            EventTransportNotRunningError: When the transport's broker client is
                not open, which happens outside the application lifecycle.
        """
        ...

    @abstractmethod
    def flush(self) -> None:
        """Block until the broker client has finished sending what send() handed over.

        A successful return means every record this caller handed over reached
        the broker. An implementation that learns of a rejection only through a
        delivery callback collects it and raises here — a caller that batches
        records has no other moment to learn that the batch did not arrive, and
        would otherwise record undelivered events as published.

        Implementations must preserve the same failure taxonomy as send(): only
        a permanent record-specific rejection becomes
        `EventDeliveryRejectedError`; transport-wide failures retain the broker
        client's original exception type.

        Raises:
            EventDeliveryRejectedError: When one or more records are permanently
                rejected for a record-specific cause.
        """
        ...


class IAsyncEventTransport(ABC):
    """Low-level asynchronous transport for pre-serialized event payloads.

    The caller owns the publish batch boundary: hand one or more payloads to
    send() and call flush() once at the end of the batch. Transports may buffer
    payloads until flush() so that broker round trips are batched. Publishers
    share one transport, so a batch's send() and flush() belong to the same
    execution context and flush() reports only that publisher's payloads.
    """

    @abstractmethod
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Hand a serialized event payload to the broker client for delivery.

        A permanent rejection attributable to this record must be reported as
        `EventDeliveryRejectedError`. A connection, timeout, queue, or other
        transport-wide failure keeps the client exception's original type so a
        caller does not spend this record's retry budget.

        Args:
            event_name: Destination topic / routing key.
            payload: Pre-serialized event bytes.
            headers: Metadata headers for trace and auth propagation.
            partition_key: Key pinning the payload to one broker partition.
                None spreads payloads round-robin.

        Raises:
            EventDeliveryRejectedError: When the transport permanently rejects
                this specific record.
            EventTransportNotRunningError: When the transport's broker client is
                not open, which happens outside the application lifecycle.
        """
        ...

    @abstractmethod
    async def flush(self) -> None:
        """Block until the broker client has finished sending what send() handed over.

        A successful return means every record this caller handed over reached
        the broker. An implementation that learns of a rejection only through a
        delivery callback collects it and raises here — a caller that batches
        records has no other moment to learn that the batch did not arrive, and
        would otherwise record undelivered events as published.

        Implementations must preserve the same failure taxonomy as send(): only
        a permanent record-specific rejection becomes
        `EventDeliveryRejectedError`; transport-wide failures retain the broker
        client's original exception type.

        Raises:
            EventDeliveryRejectedError: When one or more records are permanently
                rejected for a record-specific cause.
        """
        ...
