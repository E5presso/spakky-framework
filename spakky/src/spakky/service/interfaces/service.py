"""Protocols for application services with lifecycle management.

This module defines protocols for services that run during application lifecycle
with start and stop capabilities.
"""

from abc import abstractmethod
from asyncio import locks
from threading import Event
from typing import Protocol, runtime_checkable


@runtime_checkable
class IService(Protocol):
    """Protocol for synchronous services with lifecycle management."""

    @abstractmethod
    def set_stop_event(self, stop_event: Event) -> None:
        """Set threading event for stop signaling.

        Args:
            stop_event: Event to signal service shutdown.
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Start the service."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the service and clean up resources."""
        ...


@runtime_checkable
class IAsyncService(Protocol):
    """Protocol for asynchronous services with lifecycle management."""

    @abstractmethod
    def set_stop_event(self, stop_event: locks.Event) -> None:
        """Set async event for stop signaling.

        Args:
            stop_event: Async event to signal service shutdown.
        """
        ...

    @abstractmethod
    async def start_async(self) -> None:
        """Start the service asynchronously."""
        ...

    @abstractmethod
    async def stop_async(self) -> None:
        """Stop the service and clean up resources asynchronously."""
        ...
