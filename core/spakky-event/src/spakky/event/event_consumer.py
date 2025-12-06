from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeAlias, TypeVar

from spakky.domain.models.event import AbstractDomainEvent

DomainEventT = TypeVar("DomainEventT", bound=AbstractDomainEvent)
IEventHandlerCallback: TypeAlias = Callable[[DomainEventT], None]
IAsyncEventHandlerCallback: TypeAlias = Callable[[DomainEventT], Awaitable[None]]


class IEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[DomainEventT],
        handler: IEventHandlerCallback[DomainEventT],
    ) -> None: ...


class IAsyncEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[DomainEventT],
        handler: IAsyncEventHandlerCallback[DomainEventT],
    ) -> None: ...
