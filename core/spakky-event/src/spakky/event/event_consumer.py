from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeAlias, TypeVar

from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

DomainEventT = TypeVar("DomainEventT", bound=AbstractDomainEvent)
DomainEventHandlerCallback: TypeAlias = Callable[[DomainEventT], None]
AsyncDomainEventHandlerCallback: TypeAlias = Callable[[DomainEventT], Awaitable[None]]

IntegrationEventT = TypeVar("IntegrationEventT", bound=AbstractIntegrationEvent)
IntegrationEventHandlerCallback: TypeAlias = Callable[[IntegrationEventT], None]
AsyncIntegrationEventHandlerCallback: TypeAlias = Callable[
    [IntegrationEventT], Awaitable[None]
]


class IDomainEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[DomainEventT],
        handler: DomainEventHandlerCallback[DomainEventT],
    ) -> None: ...


class IAsyncDomainEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[DomainEventT],
        handler: AsyncDomainEventHandlerCallback[DomainEventT],
    ) -> None: ...


class IIntegrationEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[IntegrationEventT],
        handler: IntegrationEventHandlerCallback[IntegrationEventT],
    ) -> None: ...


class IAsyncIntegrationEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[IntegrationEventT],
        handler: AsyncIntegrationEventHandlerCallback[IntegrationEventT],
    ) -> None: ...
