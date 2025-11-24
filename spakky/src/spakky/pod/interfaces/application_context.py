"""Protocol and errors for application context interface.

This module defines the IApplicationContext protocol for managing
application lifecycle and service coordination.
"""

from abc import abstractmethod
from asyncio import locks
from threading import Event
from typing import Protocol, runtime_checkable

from spakky.application.error import AbstractSpakkyApplicationError
from spakky.pod.interfaces.container import IContainer
from spakky.service.interfaces.service import IAsyncService, IService


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


@runtime_checkable
class IApplicationContext(IContainer, Protocol):
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
