from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeAlias, TypeVar

from spakky.domain.models.event import AbstractEvent

EventT_contra = TypeVar("EventT_contra", bound=AbstractEvent, contravariant=True)
EventHandlerCallback: TypeAlias = Callable[[EventT_contra], None]
AsyncEventHandlerCallback: TypeAlias = Callable[[EventT_contra], Awaitable[None]]


class IEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[EventT_contra],
        handler: EventHandlerCallback[EventT_contra],
    ) -> None: ...


class IAsyncEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[EventT_contra],
        handler: AsyncEventHandlerCallback[EventT_contra],
    ) -> None: ...
