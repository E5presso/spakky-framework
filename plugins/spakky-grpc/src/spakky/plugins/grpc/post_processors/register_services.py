"""Post-processor for registering gRPC services from controllers.

Scans ``@GrpcController``-decorated Pods, builds protobuf descriptors
at runtime, and registers generic RPC handlers on the ``grpc.aio.Server``.
"""

from logging import getLogger

import grpc.aio
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.plugins.grpc.handler import GrpcServiceHandler
from spakky.plugins.grpc.schema.descriptor_builder import build_file_descriptor
from spakky.plugins.grpc.schema.registry import DescriptorRegistry
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController

logger = getLogger(__name__)


@Order(0)
@Pod()
class RegisterServicesPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Post-processor that registers gRPC services from controllers.

    When a ``@GrpcController`` Pod is created, this processor:

    1. Builds a ``FileDescriptorProto`` from the controller's ``@rpc``
       methods and dataclass message types.
    2. Registers the descriptor in the shared ``DescriptorRegistry``.
    3. Creates a ``GrpcServiceHandler`` (generic handler) and adds it
       to the ``grpc.aio.Server``.

    Runs at ``@Order(0)`` — first in the gRPC post-processor chain.
    """

    __container: IContainer
    __application_context: IApplicationContext

    def set_container(self, container: IContainer) -> None:
        """Inject the IoC container.

        Args:
            container: The IoC container.
        """
        self.__container = container

    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject the application context.

        Args:
            application_context: The application context.
        """
        self.__application_context = application_context

    def post_process(self, pod: object) -> object:
        """Register a gRPC service if *pod* is a ``@GrpcController``.

        Non-controller Pods are returned unchanged.

        Args:
            pod: The Pod instance to process.

        Returns:
            The unmodified Pod.
        """
        if not GrpcController.exists(type(pod)):
            return pod

        controller_type = type(pod)
        annotation = GrpcController.get(controller_type)
        package = annotation.package
        service_name = annotation.service_name or controller_type.__name__

        file_desc = build_file_descriptor(controller_type)

        registry = self.__container.get(DescriptorRegistry)
        if not registry.is_registered(file_desc.name):
            registry.register(file_desc)

        handler = GrpcServiceHandler(
            controller_type=controller_type,
            package=package,
            service_name=service_name,
            container=self.__container,
            application_context=self.__application_context,
            registry=registry,
        )

        server = self.__container.get(grpc.aio.Server)
        server.add_generic_rpc_handlers([handler])

        logger.info(
            f"Registered gRPC service {package}.{service_name} "
            f"from {controller_type.__qualname__}"
        )
        return pod
