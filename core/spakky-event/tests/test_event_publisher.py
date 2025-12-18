from spakky.event.event_publisher import (
    IAsyncIntegrationEventPublisher,
    IIntegrationEventPublisher,
)


def test_event_publisher_protocol() -> None:
    """Test that IIntegrationEventPublisher protocol exists"""
    assert hasattr(IIntegrationEventPublisher, "publish")


def test_async_event_publisher_protocol() -> None:
    """Test that IAsyncIntegrationEventPublisher protocol exists"""
    assert hasattr(IAsyncIntegrationEventPublisher, "publish")
