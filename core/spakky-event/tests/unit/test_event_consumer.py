from spakky.event.event_consumer import (
    IAsyncIntegrationEventConsumer,
    IIntegrationEventConsumer,
)


def test_event_consumer_protocol() -> None:
    """Test that IIntegrationEventConsumer protocol is implemented correctly"""

    # Just verify the protocol exists and can be checked
    assert hasattr(IIntegrationEventConsumer, "register")


def test_async_event_consumer_protocol() -> None:
    """Test that IAsyncIntegrationEventConsumer protocol is implemented correctly"""

    # Just verify the protocol exists and can be checked
    assert hasattr(IAsyncIntegrationEventConsumer, "register")
