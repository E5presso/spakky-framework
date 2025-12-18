from abc import ABC, abstractmethod

from spakky.domain.models.event import AbstractDomainEvent, AbstractIntegrationEvent


class IDomainEventPublisher(ABC):
    @abstractmethod
    def publish(self, event: AbstractDomainEvent) -> None: ...


class IAsyncDomainEventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: AbstractDomainEvent) -> None: ...


class IIntegrationEventPublisher(ABC):
    @abstractmethod
    def publish(self, event: AbstractIntegrationEvent) -> None: ...


class IAsyncIntegrationEventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: AbstractIntegrationEvent) -> None: ...
