from uuid import UUID

from spakky.core.mutability import immutable
from spakky.domain.models.event import AbstractDomainEvent
from spakky.pod.interfaces.application_context import IApplicationContext
from spakky.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
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
class DummyEventHandler(IApplicationContextAware):
    __application_context: IApplicationContext
    __count: int
    __context_ids: set[UUID]

    @property
    def count(self) -> int:
        return self.__count

    @property
    def context_ids(self) -> set[UUID]:
        return self.__context_ids

    def __init__(self) -> None:
        self.__count = 0
        self.__context_ids = set()

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    @on_event(SampleEvent)
    def handle_sample(self, event: SampleEvent) -> None:
        print(f"Received event: {event}")
        self.__count += 1
        self.__context_ids.add(self.__application_context.get_context_id())


@EventHandler()
class AsyncEventHandler(IApplicationContextAware):
    """Handler for testing async event consumption."""

    __application_context: IApplicationContext
    __count: int
    __context_ids: set[UUID]

    @property
    def count(self) -> int:
        return self.__count

    @property
    def context_ids(self) -> set[UUID]:
        return self.__context_ids

    def __init__(self) -> None:
        self.__count = 0
        self.__context_ids = set()

    def set_application_context(self, application_context: IApplicationContext) -> None:
        self.__application_context = application_context

    @on_event(AsyncTestEvent)
    async def handle_async_event(self, event: AsyncTestEvent) -> None:
        print(f"Async handler received event: {event}")
        self.__count += 1
        self.__context_ids.add(self.__application_context.get_context_id())
