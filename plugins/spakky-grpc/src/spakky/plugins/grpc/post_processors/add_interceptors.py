"""Post-processor for recording interceptors on the gRPC server spec.

Adds ``ErrorHandlingInterceptor`` and (when the tracing plugin is loaded)
``TracingInterceptor`` to the shared :class:`GrpcServerSpec`.  The actual
``grpc.aio.Server`` is instantiated later, on the event loop that will
run it (see :mod:`spakky.plugins.grpc.server_spec`).
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

from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor
from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor
from spakky.plugins.grpc.server_spec import GrpcServerSpec

logger = getLogger(__name__)


@Order(1)
@Pod()
class AddInterceptorsPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Post-processor that records interceptors on the shared server spec.

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
        """Record interceptors on the server spec once per spec instance.

        The spec is resolved lazily so that interceptor registration runs
        exactly once: the first time a ``GrpcServerSpec`` Pod is seen.

        Args:
            pod: The Pod instance to process.

        Returns:
            The pod unchanged.
        """
        if not isinstance(pod, GrpcServerSpec):
            return pod

        pod.add_interceptor(ErrorHandlingInterceptor())

        propagator = self.__application_context.get_or_none(ITracePropagator)
        if propagator is not None:
            pod.add_interceptor(TracingInterceptor(propagator=propagator))

        logger.info(f"Registered {len(pod.interceptors)} interceptor(s) on gRPC spec")
        return pod
