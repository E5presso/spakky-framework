from spakky.event.event_publisher import (
    IAsyncIntegrationEventPublisher,
    IIntegrationEventPublisher,
)


def test_event_publisher_protocol() -> None:
    """IIntegrationEventPublisher 프로토콜이 publish 메서드를 가짐을 검증한다."""
    assert hasattr(IIntegrationEventPublisher, "publish")


def test_async_event_publisher_protocol() -> None:
    """IAsyncIntegrationEventPublisher 프로토콜이 publish 메서드를 가짐을 검증한다."""
    assert hasattr(IAsyncIntegrationEventPublisher, "publish")
