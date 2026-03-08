from abc import ABC, abstractmethod

from spakky.domain.models.event import AbstractEvent, AbstractIntegrationEvent


class IEventPublisher(ABC):
    @abstractmethod
    def publish(self, event: AbstractEvent) -> None: ...


class IAsyncEventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: AbstractEvent) -> None: ...


class IEventBus(ABC):
    @abstractmethod
    def send(self, event: AbstractIntegrationEvent) -> None: ...


class IAsyncEventBus(ABC):
    @abstractmethod
    async def send(self, event: AbstractIntegrationEvent) -> None: ...


class IEventTransport(ABC):
    @abstractmethod
    def send(self, event: AbstractIntegrationEvent) -> None: ...


class IAsyncEventTransport(ABC):
    @abstractmethod
    async def send(self, event: AbstractIntegrationEvent) -> None: ...
