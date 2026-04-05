"""Unit tests for gRPC error hierarchy."""

import grpc
import pytest

from spakky.core.common.error import AbstractSpakkyFrameworkError
from spakky.plugins.grpc.error import (
    AbstractGrpcStatusError,
    AbstractSpakkyGrpcError,
    AlreadyExists,
    FailedPrecondition,
    InternalError,
    InvalidArgument,
    NotFound,
    PermissionDenied,
    Unauthenticated,
    Unavailable,
)


def test_abstract_spakky_grpc_error_inherits_from_framework_error() -> None:
    """AbstractSpakkyGrpcError should be a subclass of AbstractSpakkyFrameworkError."""
    assert issubclass(AbstractSpakkyGrpcError, AbstractSpakkyFrameworkError)


def test_abstract_spakky_grpc_error_is_abstract() -> None:
    """AbstractSpakkyGrpcError should be marked as ABC."""
    assert AbstractSpakkyGrpcError.__abstractmethods__ is not None


def test_abstract_grpc_status_error_inherits_from_grpc_error() -> None:
    """AbstractGrpcStatusError should be a subclass of AbstractSpakkyGrpcError."""
    assert issubclass(AbstractGrpcStatusError, AbstractSpakkyGrpcError)


@pytest.mark.parametrize(
    ("error_class", "expected_status", "expected_message"),
    [
        (InvalidArgument, grpc.StatusCode.INVALID_ARGUMENT, "Invalid Argument"),
        (NotFound, grpc.StatusCode.NOT_FOUND, "Not Found"),
        (AlreadyExists, grpc.StatusCode.ALREADY_EXISTS, "Already Exists"),
        (PermissionDenied, grpc.StatusCode.PERMISSION_DENIED, "Permission Denied"),
        (Unauthenticated, grpc.StatusCode.UNAUTHENTICATED, "Unauthenticated"),
        (
            FailedPrecondition,
            grpc.StatusCode.FAILED_PRECONDITION,
            "Failed Precondition",
        ),
        (Unavailable, grpc.StatusCode.UNAVAILABLE, "Unavailable"),
        (InternalError, grpc.StatusCode.INTERNAL, "Internal Server Error"),
    ],
)
def test_concrete_error_has_correct_status_code_and_message(
    error_class: type[AbstractGrpcStatusError],
    expected_status: grpc.StatusCode,
    expected_message: str,
) -> None:
    """Each concrete error should map to the correct gRPC status code and message."""
    assert error_class.status_code == expected_status
    assert error_class.message == expected_message


@pytest.mark.parametrize(
    "error_class",
    [
        InvalidArgument,
        NotFound,
        AlreadyExists,
        PermissionDenied,
        Unauthenticated,
        FailedPrecondition,
        Unavailable,
        InternalError,
    ],
)
def test_concrete_error_is_subclass_of_abstract_grpc_error(
    error_class: type[AbstractGrpcStatusError],
) -> None:
    """Each concrete error should be a subclass of AbstractGrpcStatusError."""
    assert issubclass(error_class, AbstractGrpcStatusError)


@pytest.mark.parametrize(
    "error_class",
    [
        InvalidArgument,
        NotFound,
        AlreadyExists,
        PermissionDenied,
        Unauthenticated,
        FailedPrecondition,
        Unavailable,
        InternalError,
    ],
)
def test_concrete_error_is_raisable(
    error_class: type[AbstractGrpcStatusError],
) -> None:
    """Each concrete error should be raisable and catchable."""
    with pytest.raises(error_class):
        raise error_class()


def test_concrete_error_caught_as_abstract_grpc_error() -> None:
    """A concrete error should be catchable as AbstractGrpcStatusError."""
    with pytest.raises(AbstractGrpcStatusError):
        raise NotFound()


def test_concrete_error_caught_as_framework_error() -> None:
    """A concrete error should be catchable as AbstractSpakkyFrameworkError."""
    with pytest.raises(AbstractSpakkyFrameworkError):
        raise InvalidArgument()
