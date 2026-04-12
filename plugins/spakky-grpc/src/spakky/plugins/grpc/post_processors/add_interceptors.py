"""Post-processor for injecting interceptors into the gRPC server.

Replaces a bare ``grpc.aio.Server`` Pod with a new server instance
that has ``ErrorHandlingInterceptor`` and (optionally)
``TracingInterceptor`` configured.
"""

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
from spakky.tracing.propagator import ITracePropagator
from typing_extensions import override

import grpc
import grpc.aio
from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor
from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor

logger = getLogger(__name__)


@Order(1)
@Pod()
class AddInterceptorsPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Post-processor that injects interceptors into the gRPC server.

    Because ``grpc.aio.Server`` requires interceptors at creation time,
    this processor creates a **new** server with the appropriate
    interceptors and returns it as a replacement for the original Pod.

    Interceptors added (in order):

    1. ``ErrorHandlingInterceptor`` — always.
    2. ``TracingInterceptor`` — only when an ``ITracePropagator`` is
       available in the application context.

    Runs at ``@Order(1)`` — after service registration.
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
        """Replace a bare ``grpc.aio.Server`` with an interceptor-equipped one.

        Non-server Pods are returned unchanged.

        Args:
            pod: The Pod instance to process.

        Returns:
            A new ``grpc.aio.Server`` with interceptors if *pod* is a
            server, otherwise the original *pod*.
        """
        if not isinstance(pod, grpc.aio.Server):
            return pod

        interceptors: list[grpc.aio.ServerInterceptor] = []
        interceptors.append(ErrorHandlingInterceptor())

        propagator = self.__application_context.get_or_none(ITracePropagator)
        if propagator is not None:
            interceptors.append(TracingInterceptor(propagator=propagator))

        new_server = grpc.aio.server(interceptors=interceptors)

        logger.info(f"Injected {len(interceptors)} interceptor(s) into gRPC server")
        return new_server
