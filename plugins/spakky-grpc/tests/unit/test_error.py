"""Unit tests for gRPC error hierarchy."""

from typing import ClassVar

from grpc import StatusCode

from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.plugins.grpc.error import (
    AbstractSpakkyGRPCError,
    AlreadyExists,
    InternalError,
    InvalidArgument,
    NotFound,
    PermissionDenied,
    Unauthenticated,
)


def test_abstract_grpc_error_inherits_framework_error() -> None:
    """AbstractSpakkyGRPCError should inherit from AbstractSpakkyFrameworkError."""
    assert issubclass(AbstractSpakkyGRPCError, AbstractSpakkyFrameworkError)


def test_invalid_argument_maps_to_invalid_argument_status() -> None:
    """InvalidArgument should map to StatusCode.INVALID_ARGUMENT."""
    assert InvalidArgument.status_code == StatusCode.INVALID_ARGUMENT


def test_not_found_maps_to_not_found_status() -> None:
    """NotFound should map to StatusCode.NOT_FOUND."""
    assert NotFound.status_code == StatusCode.NOT_FOUND


def test_already_exists_maps_to_already_exists_status() -> None:
    """AlreadyExists should map to StatusCode.ALREADY_EXISTS."""
    assert AlreadyExists.status_code == StatusCode.ALREADY_EXISTS


def test_permission_denied_maps_to_permission_denied_status() -> None:
    """PermissionDenied should map to StatusCode.PERMISSION_DENIED."""
    assert PermissionDenied.status_code == StatusCode.PERMISSION_DENIED


def test_unauthenticated_maps_to_unauthenticated_status() -> None:
    """Unauthenticated should map to StatusCode.UNAUTHENTICATED."""
    assert Unauthenticated.status_code == StatusCode.UNAUTHENTICATED


def test_internal_error_maps_to_internal_status() -> None:
    """InternalError should map to StatusCode.INTERNAL."""
    assert InternalError.status_code == StatusCode.INTERNAL


def test_grpc_error_message_attribute() -> None:
    """Concrete gRPC error classes should have a message attribute."""
    assert InvalidArgument.message == "Invalid Argument"
    assert NotFound.message == "Not Found"
    assert AlreadyExists.message == "Already Exists"
    assert PermissionDenied.message == "Permission Denied"
    assert Unauthenticated.message == "Unauthenticated"
    assert InternalError.message == "Internal Error"


def test_grpc_error_is_raisable() -> None:
    """Concrete gRPC error classes should be raisable as exceptions."""
    try:
        raise NotFound()
    except AbstractSpakkyGRPCError as e:
        assert e.status_code == StatusCode.NOT_FOUND
        assert e.message == "Not Found"


def test_custom_grpc_error_enforces_status_code() -> None:
    """Custom subclass of AbstractSpakkyGRPCError should define status_code."""

    class CustomError(AbstractSpakkyGRPCError):
        message = "Custom Error"
        status_code: ClassVar[StatusCode] = StatusCode.UNAVAILABLE

    error = CustomError()
    assert error.status_code == StatusCode.UNAVAILABLE
    assert error.message == "Custom Error"
