"""Protocols for application services with lifecycle management.

This module defines protocols for services that run during application lifecycle
with start and stop capabilities.
"""

import threading
from abc import ABC, abstractmethod
from asyncio import locks


class IService(ABC):
    """Protocol for synchronous services with lifecycle management."""

    @abstractmethod
    def set_stop_event(self, stop_event: threading.Event) -> None:
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


class IAsyncService(ABC):
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
