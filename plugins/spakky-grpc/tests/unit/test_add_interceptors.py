"""Unit tests for AddInterceptorsPostProcessor."""

from unittest.mock import MagicMock

import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor
from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor
from spakky.plugins.grpc.post_processors.add_interceptors import (
    AddInterceptorsPostProcessor,
)
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from spakky.tracing.propagator import ITracePropagator


@pytest.fixture
def processor() -> AddInterceptorsPostProcessor:
    """Create a configured AddInterceptorsPostProcessor (no tracing)."""
    proc = AddInterceptorsPostProcessor.__new__(AddInterceptorsPostProcessor)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    application_context.get_or_none = MagicMock(return_value=None)
    proc.set_container(container)
    proc.set_application_context(application_context)
    return proc


@pytest.fixture
def processor_with_tracing() -> AddInterceptorsPostProcessor:
    """Create AddInterceptorsPostProcessor with a trace propagator available."""
    proc = AddInterceptorsPostProcessor.__new__(AddInterceptorsPostProcessor)
    container = MagicMock(spec=IContainer)
    propagator = MagicMock(spec=ITracePropagator)
    application_context = MagicMock(spec=IApplicationContext)
    application_context.get_or_none = MagicMock(return_value=propagator)
    proc.set_container(container)
    proc.set_application_context(application_context)
    return proc


def test_add_interceptors_with_non_spec_pod_expect_unchanged(
    processor: AddInterceptorsPostProcessor,
) -> None:
    """Non-spec Pods should be returned unchanged."""
    plain_pod = object()
    result = processor.post_process(plain_pod)
    assert result is plain_pod


def test_add_interceptors_with_spec_and_no_propagator_expect_error_handler_only(
    processor: AddInterceptorsPostProcessor,
) -> None:
    """Spec Pod should receive an ErrorHandlingInterceptor when tracing is off."""
    spec = GrpcServerSpec()

    result = processor.post_process(spec)

    assert result is spec
    assert len(spec.interceptors) == 1
    assert isinstance(spec.interceptors[0], ErrorHandlingInterceptor)


def test_add_interceptors_with_propagator_available_expect_tracing_added(
    processor_with_tracing: AddInterceptorsPostProcessor,
) -> None:
    """Spec Pod should receive both error and tracing interceptors when available."""
    spec = GrpcServerSpec()

    processor_with_tracing.post_process(spec)

    assert len(spec.interceptors) == 2
    assert isinstance(spec.interceptors[0], ErrorHandlingInterceptor)
    assert isinstance(spec.interceptors[1], TracingInterceptor)
