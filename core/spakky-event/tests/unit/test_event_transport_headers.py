"""Unit tests for IEventTransport/IAsyncEventTransport headers parameter."""

import pytest

from spakky.event.event_publisher import IAsyncEventTransport, IEventTransport


class StubTransport(IEventTransport):
    """Stub transport that records call arguments."""

    def __init__(self) -> None:
        self.last_headers: dict[str, str] = {}
        self.called: bool = False

    def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.called = True
        self.last_headers = headers


class AsyncStubTransport(IAsyncEventTransport):
    """Async stub transport that records call arguments."""

    def __init__(self) -> None:
        self.last_headers: dict[str, str] = {}
        self.called: bool = False

    async def send(
        self,
        event_name: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> None:
        self.called = True
        self.last_headers = headers


def test_transport_send_with_empty_headers_expect_empty_dict() -> None:
    """IEventTransport 구현체에 빈 headers를 전달하면 빈 dict가 수신됨을 검증한다."""
    transport = StubTransport()

    transport.send("TestEvent", b'{"data": "test"}', {})

    assert transport.called is True
    assert transport.last_headers == {}


def test_transport_send_with_headers_expect_headers_received() -> None:
    """IEventTransport 구현체에 headers를 전달하면 수신됨을 검증한다."""
    transport = StubTransport()
    headers = {"traceparent": "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"}

    transport.send("TestEvent", b'{"data": "test"}', headers=headers)

    assert transport.called is True
    assert transport.last_headers["traceparent"] == headers["traceparent"]


@pytest.mark.asyncio
async def test_async_transport_send_with_empty_headers_expect_empty_dict() -> None:
    """IAsyncEventTransport 구현체에 빈 headers를 전달하면 빈 dict가 수신됨을 검증한다."""
    transport = AsyncStubTransport()

    await transport.send("TestEvent", b'{"data": "test"}', {})

    assert transport.called is True
    assert transport.last_headers == {}


@pytest.mark.asyncio
async def test_async_transport_send_with_headers_expect_headers_received() -> None:
    """IAsyncEventTransport 구현체에 headers를 전달하면 수신됨을 검증한다."""
    transport = AsyncStubTransport()
    headers = {"traceparent": "00-abcd1234abcd1234abcd1234abcd1234-1234abcd1234abcd-01"}

    await transport.send("TestEvent", b'{"data": "test"}', headers=headers)

    assert transport.called is True
    assert transport.last_headers["traceparent"] == headers["traceparent"]
