"""Post-processor for binding gRPC server lifecycle.

Wires a :class:`GrpcServerSpec` Pod into the ``ApplicationContext`` so
that the underlying ``grpc.aio.Server`` is materialised on the context's
event loop and started/stopped alongside the application.
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
from spakky.plugins.grpc.server_spec import GrpcServerSpec

logger = getLogger(__name__)

GRACEFUL_SHUTDOWN_SECONDS: float = 5.0
"""Default grace period (seconds) for server shutdown."""


class GrpcServerService(IAsyncService):
    """Async service wrapper that instantiates the gRPC server on the right loop.

    ``grpc.aio.server()`` binds to whatever event loop is running when it
    is called, so the real server is created inside :meth:`start_async`
    from the captured :class:`GrpcServerSpec`.

    Attributes:
        _spec: Configuration collected during post-processing.
        _server: The materialised server, set once :meth:`start_async` runs.
        _stop_event: Async event passed by the application context; unused
            internally because shutdown is driven by :meth:`stop_async`, but
            retained to satisfy the :class:`IAsyncService` contract.
    """

    _spec: GrpcServerSpec
    _server: grpc.aio.Server | None
    _stop_event: locks.Event

    def __init__(self, spec: GrpcServerSpec) -> None:
        """Initialise the service with a server spec.

        Args:
            spec: Collected server configuration.
        """
        self._spec = spec
        self._server = None

    @override
    def set_stop_event(self, stop_event: locks.Event) -> None:
        """Store the async stop event from the application context.

        Args:
            stop_event: Async event forwarded by the application context.
        """
        self._stop_event = stop_event

    @override
    async def start_async(self) -> None:
        """Build the gRPC server on the current loop and start it."""
        self._server = self._spec.build()
        await self._server.start()
        logger.info("gRPC server started")

    @override
    async def stop_async(self) -> None:
        """Gracefully stop the gRPC server if it was started.

        Clears ``_server`` after a successful stop so that repeated
        ``stop_async`` calls are safe no-ops.
        """
        if self._server is None:
            return
        server = self._server
        self._server = None
        await server.stop(grace=GRACEFUL_SHUTDOWN_SECONDS)
        logger.info("gRPC server stopped")


@Order(2)
@Pod()
class BindServerPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Post-processor that binds a :class:`GrpcServerSpec` to the ApplicationContext.

    Wraps the spec in a :class:`GrpcServerService` and registers it with
    the ``ApplicationContext`` for automatic start/stop management.

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
        """Bind server lifecycle if *pod* is a ``GrpcServerSpec``.

        Non-spec Pods are returned unchanged.

        Args:
            pod: The Pod instance to process.

        Returns:
            The unmodified spec Pod.
        """
        if not isinstance(pod, GrpcServerSpec):
            return pod

        service = GrpcServerService(pod)
        service.set_stop_event(self.__application_context.task_stop_event)
        self.__application_context.add_service(service)
        logger.info("Bound gRPC server lifecycle to ApplicationContext")
        return pod
