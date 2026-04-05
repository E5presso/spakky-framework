"""Unit tests for GrpcController stereotype."""

from spakky.core.pod.annotations.pod import Pod
from spakky.core.stereotype.controller import Controller
from spakky.plugins.grpc.stereotypes.grpc_controller import GrpcController


def test_grpc_controller_registers_class_as_pod() -> None:
    """GrpcController should register a class as a Pod."""

    @GrpcController(package="example.v1")
    class GreeterService:
        pass

    assert Pod.exists(GreeterService)


def test_grpc_controller_registers_class_as_controller() -> None:
    """GrpcController should register a class as a Controller."""

    @GrpcController(package="example.v1")
    class GreeterService:
        pass

    assert Controller.exists(GreeterService)


def test_grpc_controller_stores_package_field() -> None:
    """GrpcController should store the protobuf package name."""

    @GrpcController(package="example.v1")
    class GreeterService:
        pass

    annotation = GrpcController.get(GreeterService)
    assert annotation.package == "example.v1"


def test_grpc_controller_auto_generates_service_name_from_class_name() -> None:
    """GrpcController should use the class name as service_name when not provided."""

    @GrpcController(package="example.v1")
    class GreeterService:
        pass

    annotation = GrpcController.get(GreeterService)
    assert annotation.service_name == "GreeterService"


def test_grpc_controller_uses_explicit_service_name() -> None:
    """GrpcController should use the explicit service_name when provided."""

    @GrpcController(package="example.v1", service_name="Greeter")
    class GreeterService:
        pass

    annotation = GrpcController.get(GreeterService)
    assert annotation.service_name == "Greeter"


def test_grpc_controller_annotation_is_retrievable() -> None:
    """GrpcController annotation should be retrievable from the class."""

    @GrpcController(package="myapp.v1", service_name="UserService")
    class UserController:
        pass

    annotation = GrpcController.get(UserController)
    assert annotation.package == "myapp.v1"
    assert annotation.service_name == "UserService"
