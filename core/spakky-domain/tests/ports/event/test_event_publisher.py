from spakky.domain.ports.event.event_publisher import (
    IAsyncEventPublisher,
    IEventPublisher,
)


def test_event_publisher_protocol() -> None:
    """Test that IEventPublisher protocol exists"""
    assert hasattr(IEventPublisher, "publish")


def test_async_event_publisher_protocol() -> None:
    """Test that IAsyncEventPublisher protocol exists"""
    assert hasattr(IAsyncEventPublisher, "publish")
