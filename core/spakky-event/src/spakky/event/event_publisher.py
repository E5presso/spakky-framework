from abc import ABC, abstractmethod

from spakky.domain.models.event import AbstractDomainEvent


class IEventPublisher(ABC):
    @abstractmethod
    def publish(self, event: AbstractDomainEvent) -> None: ...


class IAsyncEventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: AbstractDomainEvent) -> None: ...
