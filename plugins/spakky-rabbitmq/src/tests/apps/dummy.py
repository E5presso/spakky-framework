from spakky.core.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent
from spakky.stereotype.event_handler import EventHandler, on_event


@immutable
class SampleEvent(AbstractDomainEvent):
    message: str


@immutable
class DuplicateTestEvent(AbstractDomainEvent):
    """Event for duplicate handler registration tests."""

    data: str


@immutable
class AsyncTestEvent(AbstractDomainEvent):
    """Event for async handler tests."""

    message: str


@EventHandler()
class DummyEventHandler:
    __count: int

    @property
    def count(self) -> int:
        return self.__count

    def __init__(self) -> None:
        self.__count = 0

    @on_event(SampleEvent)
    def handle_sample(self, event: SampleEvent) -> None:
        print(f"Received event: {event}")
        self.__count += 1


@EventHandler()
class AsyncEventHandler:
    """Handler for testing async event consumption."""

    __count: int

    @property
    def count(self) -> int:
        return self.__count

    def __init__(self) -> None:
        self.__count = 0

    @on_event(AsyncTestEvent)
    async def handle_async_event(self, event: AsyncTestEvent) -> None:
        print(f"Async handler received event: {event}")
        self.__count += 1
