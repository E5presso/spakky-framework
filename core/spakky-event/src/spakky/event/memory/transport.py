"""Transports that publish serialized integration events into the in-memory broker."""

from typing import override

from spakky.core.pod.annotations.pod import Pod

from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport
from spakky.event.memory.broker import InMemoryEventBroker, InMemoryMessage


@Pod()
class InMemoryEventTransport(IEventTransport):
    """Synchronous transport backed by `InMemoryEventBroker`."""

    _broker: InMemoryEventBroker

    def __init__(self, broker: InMemoryEventBroker) -> None:
        self._broker = broker

    @override
    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Publish the payload to every subscriber queue of `event_name`."""
        self._broker.publish(
            InMemoryMessage(
                event_name=event_name,
                payload=payload,
                headers=dict(headers),
                partition_key=partition_key,
            )
        )

    @override
    def flush(self) -> None:
        """Nothing is buffered; `send` already published."""
        return


@Pod()
class AsyncInMemoryEventTransport(IAsyncEventTransport):
    """Asynchronous transport backed by `InMemoryEventBroker`."""

    _broker: InMemoryEventBroker

    def __init__(self, broker: InMemoryEventBroker) -> None:
        self._broker = broker

    @override
    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
        partition_key: str | None = None,
    ) -> None:
        """Publish the payload to every subscriber queue of `event_name`."""
        self._broker.publish(
            InMemoryMessage(
                event_name=event_name,
                payload=payload,
                headers=dict(headers),
                partition_key=partition_key,
            )
        )

    @override
    async def flush(self) -> None:
        """Nothing is buffered; `send` already published."""
        return
