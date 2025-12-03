from abc import abstractmethod

from spakky_ddd.models.event import AbstractDomainEvent


class IEventPublisher:
    @abstractmethod
    def publish(self, event: AbstractDomainEvent) -> None: ...


class IAsyncEventPublisher:
    @abstractmethod
    async def publish(self, event: AbstractDomainEvent) -> None: ...
