from spakky.event.event_consumer import (
    IAsyncEventConsumer,
    IEventConsumer,
)


def test_event_consumer_interface() -> None:
    """IEventConsumer 인터페이스가 올바르게 정의되어 있음을 검증한다."""
    assert hasattr(IEventConsumer, "register")


def test_async_event_consumer_interface() -> None:
    """IAsyncEventConsumer 인터페이스가 올바르게 정의되어 있음을 검증한다."""
    assert hasattr(IAsyncEventConsumer, "register")
