"""Post-processor for binding gRPC server lifecycle.

Wraps the ``grpc.aio.Server`` lifecycle so that it starts and stops
together with the Spakky ``ApplicationContext``.
"""

from asyncio import locks
from logging import getLogger

from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.core.service.interfaces.service import IAsyncService
from typing_extensions import override

import grpc.aio

logger = getLogger(__name__)

GRACEFUL_SHUTDOWN_SECONDS: float = 5.0
"""Default grace period (seconds) for server shutdown."""


class GrpcServerService(IAsyncService):
    """Async service wrapper for ``grpc.aio.Server`` lifecycle.

    Registers with the ``ApplicationContext`` so that the gRPC server
    starts and stops together with the application.

    Attributes:
        _server: The gRPC async server to manage.
        _stop_event: Async event signalled when the application stops.
    """

    _server: grpc.aio.Server
    _stop_event: locks.Event

    def __init__(self, server: grpc.aio.Server) -> None:
        """Initialise with the target server.

        Args:
            server: The gRPC async server to manage.
        """
        self._server = server

    def set_stop_event(self, stop_event: locks.Event) -> None:
        """Set the async stop event.

        Args:
            stop_event: Async event to signal service shutdown.
        """
        self._stop_event = stop_event

    @override
    async def start_async(self) -> None:
        """Start the gRPC server."""
        await self._server.start()
        logger.info("gRPC server started")

    @override
    async def stop_async(self) -> None:
        """Gracefully stop the gRPC server."""
        await self._server.stop(grace=GRACEFUL_SHUTDOWN_SECONDS)
        logger.info("gRPC server stopped")


@Order(2)
@Pod()
class BindServerPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Post-processor that binds gRPC server lifecycle to ApplicationContext.

    Wraps the ``grpc.aio.Server`` in a ``GrpcServerService`` and
    registers it with the ``ApplicationContext`` for automatic
    start/stop management.

    Runs at ``@Order(2)`` — last in the gRPC post-processor chain.
    """

    __container: IContainer
    __application_context: IApplicationContext

    @override
    def set_container(self, container: IContainer) -> None:
        """Inject the IoC container.

        Args:
            container: The IoC container.
        """
        self.__container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject the application context.

        Args:
            application_context: The application context.
        """
        self.__application_context = application_context

    @override
    def post_process(self, pod: object) -> object:
        """Bind server lifecycle if *pod* is a ``grpc.aio.Server``.

        Non-server Pods are returned unchanged.

        Args:
            pod: The Pod instance to process.

        Returns:
            The unmodified Pod.
        """
        if not isinstance(pod, grpc.aio.Server):
            return pod

        service = GrpcServerService(pod)
        service.set_stop_event(self.__application_context.task_stop_event)
        self.__application_context.add_service(service)
        logger.info("Bound gRPC server lifecycle to ApplicationContext")
        return pod
