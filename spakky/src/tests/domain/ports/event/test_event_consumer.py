from spakky.domain.ports.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)


def test_event_consumer_protocol() -> None:
    """Test that IEventConsumer protocol is implemented correctly"""

    # Just verify the protocol exists and can be checked
    assert hasattr(IEventConsumer, "register")


def test_async_event_consumer_protocol() -> None:
    """Test that IAsyncEventConsumer protocol is implemented correctly"""

    # Just verify the protocol exists and can be checked
    assert hasattr(IAsyncEventConsumer, "register")
