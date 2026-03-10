from spakky.event.event_publisher import (
    IAsyncEventBus,
    IAsyncEventPublisher,
    IAsyncEventTransport,
    IEventBus,
    IEventPublisher,
    IEventTransport,
)


def test_event_publisher_protocol() -> None:
    """IEventPublisher 프로토콜이 publish 메서드를 가짐을 검증한다."""
    assert hasattr(IEventPublisher, "publish")


def test_async_event_publisher_protocol() -> None:
    """IAsyncEventPublisher 프로토콜이 publish 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncEventPublisher, "publish")


def test_event_bus_protocol() -> None:
    """IEventBus 프로토콜이 send 메서드를 가짐을 검증한다."""
    assert hasattr(IEventBus, "send")


def test_async_event_bus_protocol() -> None:
    """IAsyncEventBus 프로토콜이 send 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncEventBus, "send")


def test_event_transport_protocol() -> None:
    """IEventTransport 프로토콜이 send 메서드를 가짐을 검증한다."""
    assert hasattr(IEventTransport, "send")


def test_async_event_transport_protocol() -> None:
    """IAsyncEventTransport 프로토콜이 send 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncEventTransport, "send")
