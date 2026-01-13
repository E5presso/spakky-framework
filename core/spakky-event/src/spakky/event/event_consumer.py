from abc import ABC, abstractmethod
from typing import Awaitable, Callable, TypeAlias, TypeVar

from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent

DomainEventT = TypeVar("DomainEventT", bound=AbstractDomainEvent)
DomainEventT_co = TypeVar("DomainEventT_co", bound=AbstractDomainEvent, covariant=True)
DomainEventT_contra = TypeVar(
    "DomainEventT_contra", bound=AbstractDomainEvent, contravariant=True
)
DomainEventHandlerCallback: TypeAlias = Callable[[DomainEventT_contra], None]
AsyncDomainEventHandlerCallback: TypeAlias = Callable[
    [DomainEventT_contra], Awaitable[None]
]

IntegrationEventT = TypeVar("IntegrationEventT", bound=AbstractIntegrationEvent)
IntegrationEventT_co = TypeVar(
    "IntegrationEventT_co", bound=AbstractIntegrationEvent, covariant=True
)
IntegrationEventT_contra = TypeVar(
    "IntegrationEventT_contra", bound=AbstractIntegrationEvent, contravariant=True
)
IntegrationEventHandlerCallback: TypeAlias = Callable[[IntegrationEventT_contra], None]
AsyncIntegrationEventHandlerCallback: TypeAlias = Callable[
    [IntegrationEventT_contra], Awaitable[None]
]


class IDomainEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[DomainEventT_contra],
        handler: DomainEventHandlerCallback[DomainEventT_contra],
    ) -> None: ...


class IAsyncDomainEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[DomainEventT_contra],
        handler: AsyncDomainEventHandlerCallback[DomainEventT_contra],
    ) -> None: ...


class IIntegrationEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[IntegrationEventT_contra],
        handler: IntegrationEventHandlerCallback[IntegrationEventT_contra],
    ) -> None: ...


class IAsyncIntegrationEventConsumer(ABC):
    @abstractmethod
    def register(
        self,
        event: type[IntegrationEventT_contra],
        handler: AsyncIntegrationEventHandlerCallback[IntegrationEventT_contra],
    ) -> None: ...
