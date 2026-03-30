"""Unit tests for DirectEventBus/AsyncDirectEventBus trace propagation."""

import pytest
from spakky.core.common.mutability import immutable
from spakky.domain.models.event import AbstractIntegrationEvent
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

from spakky.event.bus.transport_event_bus import AsyncDirectEventBus, DirectEventBus
from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


@immutable
class SampleIntegrationEvent(AbstractIntegrationEvent):
    """Sample integration event for testing."""

    message: str


class RecordingTransport(IEventTransport):
    """Transport that records sent events with headers."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload, headers))


class AsyncRecordingTransport(IAsyncEventTransport):
    """Async transport that records sent events with headers."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.sent.append((event_name, payload, headers))


class FakePropagator(ITracePropagator):
    """Fake propagator that injects a fixed traceparent header."""

    def inject(self, carrier: dict[str, str]) -> None:
        carrier["traceparent"] = (
            "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
        )

    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        return None

    def fields(self) -> list[str]:
        return ["traceparent"]


# ── Sync tests ──


def test_direct_event_bus_with_propagator_expect_headers_injected() -> None:
    """propagator가 있을 때 transport.send에 traceparent 헤더가 포함됨을 검증한다."""
    transport = RecordingTransport()
    propagator = FakePropagator()
    bus = DirectEventBus(transport, propagator)

    event = SampleIntegrationEvent(message="traced")
    bus.send(event)

    assert len(transport.sent) == 1
    _, _, headers = transport.sent[0]
    assert headers is not None
    assert "traceparent" in headers
    assert (
        headers["traceparent"]
        == "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
    )


# ── Async tests ──


@pytest.mark.asyncio
async def test_async_direct_event_bus_with_propagator_expect_headers_injected() -> None:
    """async propagator가 있을 때 transport.send에 traceparent 헤더가 포함됨을 검증한다."""
    transport = AsyncRecordingTransport()
    propagator = FakePropagator()
    bus = AsyncDirectEventBus(transport, propagator)

    event = SampleIntegrationEvent(message="async-traced")
    await bus.send(event)

    assert len(transport.sent) == 1
    _, _, headers = transport.sent[0]
    assert headers is not None
    assert "traceparent" in headers
    assert (
        headers["traceparent"]
        == "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"
    )
