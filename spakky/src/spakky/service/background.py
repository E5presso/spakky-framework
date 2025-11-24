"""Abstract base classes for background services.

This module provides base implementations for long-running background
services with proper lifecycle management.
"""

from abc import ABC, abstractmethod
from asyncio import locks, tasks
from threading import Event as ThreadEvent
from threading import Thread

from spakky.service.interfaces.service import IAsyncService, IService


class AbstractBackgroundService(IService, ABC):
    """Base class for synchronous background services.

    Runs in a dedicated thread and can be started/stopped gracefully.
    """

    _thread: Thread | None
    _stop_event: ThreadEvent

    def set_stop_event(self, stop_event: ThreadEvent) -> None:
        """Set stop event for shutdown signaling.

        Args:
            stop_event: Event to signal service shutdown.
        """
        self._stop_event = stop_event

    def start(self) -> None:
        """Start service in background thread."""
        self._stop_event.clear()
        self.initialize()
        self._thread = Thread(target=self.run, daemon=True, name=type(self).__name__)
        self._thread.start()

    def stop(self) -> None:
        """Stop service and wait for thread to finish."""
        self._stop_event.set()
        if self._thread:  # pragma: no cover
            self._thread.join()
        self.dispose()

    @abstractmethod
    def initialize(self) -> None:
        """Initialize service before starting.

        Called once before the service thread starts.
        """
        ...

    @abstractmethod
    def dispose(self) -> None:
        """Clean up resources after stopping.

        Called once after the service thread stops.
        """
        ...

    @abstractmethod
    def run(self) -> None:
        """Main service loop.

        Runs in background thread. Should check _stop_event periodically
        and exit when it's set.
        """
        ...


class AbstractAsyncBackgroundService(IAsyncService, ABC):
    """Base class for asynchronous background services.

    Runs as an async task and can be started/stopped gracefully.
    """

    _task: tasks.Task[None] | None
    _stop_event: locks.Event

    def set_stop_event(self, stop_event: locks.Event) -> None:
        """Set stop event for shutdown signaling.

        Args:
            stop_event: Async event to signal service shutdown.
        """
        self._stop_event = stop_event

    async def start_async(self) -> None:
        """Start service as background task."""
        self._stop_event.clear()
        await self.initialize_async()
        self._task = tasks.create_task(coro=self.run_async(), name=type(self).__name__)

    async def stop_async(self) -> None:
        """Stop service and wait for task to finish."""
        self._stop_event.set()
        if self._task:  # pragma: no cover
            await self._task
        await self.dispose_async()

    @abstractmethod
    async def initialize_async(self) -> None:
        """Initialize service before starting.

        Called once before the service task starts.
        """
        ...

    @abstractmethod
    async def dispose_async(self) -> None:
        """Clean up resources after stopping.

        Called once after the service task stops.
        """
        ...

    @abstractmethod
    async def run_async(self) -> None:
        """Main service loop.

        Runs as async task. Should check _stop_event periodically
        and exit when it's set.
        """
        ...
