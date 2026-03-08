"""Mock IAsyncEventTransport and IEventTransport for integration testing."""

from spakky.core.pod.annotations.pod import Pod
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


@Pod()
class MockEventTransport(IEventTransport):
    """No-op sync transport for integration tests."""

    sent_events: list[AbstractIntegrationEvent]

    def __init__(self) -> None:
        self.sent_events = []

    def send(self, event: AbstractIntegrationEvent) -> None:
        """Record the event for assertion in tests."""
        self.sent_events.append(event)


@Pod()
class MockAsyncEventTransport(IAsyncEventTransport):
    """No-op async transport for integration tests.

    Collects sent events in memory without forwarding to any broker.
    """

    sent_events: list[AbstractIntegrationEvent]

    def __init__(self) -> None:
        self.sent_events = []

    async def send(self, event: AbstractIntegrationEvent) -> None:
        """Record the event for assertion in tests."""
        self.sent_events.append(event)
