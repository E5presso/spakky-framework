"""Opt-in registration of the in-memory integration event broker."""

from spakky.core.application.application import SpakkyApplication

from spakky.event.memory.broker import InMemoryEventBroker
from spakky.event.memory.config import InMemoryEventConfig
from spakky.event.memory.consumer import (
    AsyncInMemoryEventConsumer,
    InMemoryEventConsumer,
)
from spakky.event.memory.post_processor import InMemoryEventPostProcessor
from spakky.event.memory.transport import (
    AsyncInMemoryEventTransport,
    InMemoryEventTransport,
)


def initialize(app: SpakkyApplication) -> None:
    """Register the in-memory broker as the integration event provider.

    This is not a plugin entry point and is never loaded automatically: call it
    explicitly, and do not combine it with a broker plugin in one application.

    Args:
        app: Application that should run integration events in memory.
    """
    app.add(InMemoryEventConfig)
    app.add(InMemoryEventBroker)
    app.add(InMemoryEventTransport)
    app.add(AsyncInMemoryEventTransport)
    app.add(InMemoryEventConsumer)
    app.add(AsyncInMemoryEventConsumer)
    app.add(InMemoryEventPostProcessor)
