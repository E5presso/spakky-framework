"""gRPC controller stereotype for service grouping.

Provides the @GrpcController stereotype for marking classes as gRPC service
controllers with automatic service registration and protobuf package configuration.
"""

from dataclasses import dataclass

from spakky.core.common.types import AnyT
from spakky.core.stereotype.controller import Controller


@dataclass(eq=False)
class GrpcController(Controller):
    """Stereotype for gRPC service controllers.

    Marks a class as a gRPC service controller with automatic service
    registration. Methods decorated with @rpc will be registered as gRPC
    service methods.

    Attributes:
        package: Protobuf package name for the service.
        service_name: gRPC service name. Defaults to the class name if not
            provided.
    """

    package: str
    """Protobuf package name for the service."""

    service_name: str | None = None
    """gRPC service name. Defaults to the class name."""

    def __call__(self, obj: AnyT) -> AnyT:
        """Apply the gRPC controller stereotype to a class.

        Automatically generates the service name from the class name
        if not provided.

        Args:
            obj: The class to decorate.

        Returns:
            The decorated class registered as a Pod.
        """
        if self.service_name is None:
            self.service_name = obj.__name__  # type: ignore[union-attr] - 제네릭 AnyT가 클래스 타입으로 좁혀지지 않아 __name__ 접근 오탐
        return super().__call__(obj)
