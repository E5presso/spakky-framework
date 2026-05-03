from spakky.event.event_publisher import (
    IAsyncEventBus,
    IAsyncEventPublisher,
    IAsyncEventTransport,
    IEventBus,
    IEventPublisher,
    IEventTransport,
)


def test_event_publisher_interface() -> None:
    """IEventPublisher 인터페이스가 publish 메서드를 가짐을 검증한다."""
    assert hasattr(IEventPublisher, "publish")


def test_async_event_publisher_interface() -> None:
    """IAsyncEventPublisher 인터페이스가 publish 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncEventPublisher, "publish")


def test_event_bus_interface() -> None:
    """IEventBus 인터페이스가 send 메서드를 가짐을 검증한다."""
    assert hasattr(IEventBus, "send")


def test_async_event_bus_interface() -> None:
    """IAsyncEventBus 인터페이스가 send 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncEventBus, "send")


def test_event_transport_interface() -> None:
    """IEventTransport 인터페이스가 send 메서드를 가짐을 검증한다."""
    assert hasattr(IEventTransport, "send")


def test_async_event_transport_interface() -> None:
    """IAsyncEventTransport 인터페이스가 send 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncEventTransport, "send")
