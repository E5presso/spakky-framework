"""Protocol and errors for application context interface.

This module defines the IApplicationContext protocol for managing
application lifecycle and service coordination.
"""

from abc import ABC, abstractmethod
from asyncio import locks
from threading import Event
from uuid import UUID

from spakky.core.application.error import AbstractSpakkyApplicationError
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.service.interfaces.service import IAsyncService, IService


class ApplicationContextAlreadyStartedError(AbstractSpakkyApplicationError):
    """Raised when attempting to start an already started context."""

    message = "Application context already started"


class ApplicationContextAlreadyStoppedError(AbstractSpakkyApplicationError):
    """Raised when attempting to stop an already stopped context."""

    message = "Application context already stopped"


class EventLoopThreadNotStartedInApplicationContextError(
    AbstractSpakkyApplicationError
):
    """Raised when event loop thread is not running but required."""

    message = "Event loop thread not started in application context"


class EventLoopThreadAlreadyStartedInApplicationContextError(
    AbstractSpakkyApplicationError
):
    """Raised when attempting to start already running event loop thread."""

    message = "Event loop thread already started in application context"


class IApplicationContext(IContainer, ABC):
    """Protocol for application context managing Pod lifecycle and services.

    Extends IContainer with service management and lifecycle control.
    """

    thread_stop_event: Event
    """Threading event for stopping background threads."""

    task_stop_event: locks.Event
    """Async event for stopping background tasks."""

    @property
    @abstractmethod
    def is_started(self) -> bool:
        """Check if context is started.

        Returns:
            True if context has been started.
        """
        ...

    @abstractmethod
    def add_service(self, service: IService | IAsyncService) -> None:
        """Register a service for lifecycle management.

        Args:
            service: The service to register.
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Start the application context and all services."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the application context and clean up resources."""
        ...

    @abstractmethod
    def get_context_id(self) -> UUID:
        """Get unique ID for current context.

        Returns:
            UUID for this context.
        """
        ...

    @abstractmethod
    def get_context_value(self, key: str) -> object | None:
        """Get a value from the context-scoped cache.

        Args:
            key: The key to retrieve.

        Returns:
            The cached value, or None if not found.
        """
        ...

    @abstractmethod
    def set_context_value(self, key: str, value: object) -> None:
        """Set a value in the context-scoped cache.

        Args:
            key: The key to set.
            value: The value to store.
        """
        ...

    @abstractmethod
    def clear_context(self) -> None:
        """Clear context-scoped cache for current context."""
        ...
