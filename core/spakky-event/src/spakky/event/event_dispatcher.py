"""Event dispatcher interfaces for dispatching events to registered handlers.

This module provides unified dispatcher interfaces that handle all event types.
Dispatchers are responsible for delivering events to registered handlers, while
Consumers are responsible for handler registration. These interfaces are combined
in Mediator implementations.
"""

from abc import ABC, abstractmethod

from spakky.domain.models.event import AbstractEvent


class IEventDispatcher(ABC):
    @abstractmethod
    def dispatch(self, event: AbstractEvent) -> None: ...


class IAsyncEventDispatcher(ABC):
    @abstractmethod
    async def dispatch(self, event: AbstractEvent) -> None: ...
