from spakky.event.event_consumer import (
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)


def test_event_consumer_protocol() -> None:
    """IIntegrationEventConsumer 프로토콜이 올바르게 정의되어 있음을 검증한다."""
    # Just verify the protocol exists and can be checked
    assert hasattr(IIntegrationEventConsumer, "register")


def test_async_event_consumer_protocol() -> None:
    """IAsyncIntegrationEventConsumer 프로토콜이 올바르게 정의되어 있음을 검증한다."""
    # Just verify the protocol exists and can be checked
    assert hasattr(IAsyncIntegrationEventConsumer, "register")
