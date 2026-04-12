"""Unit tests for AddInterceptorsPostProcessor."""

from unittest.mock import MagicMock, patch

import grpc.aio
import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.interceptors.error_handling import ErrorHandlingInterceptor
from spakky.plugins.grpc.interceptors.tracing import TracingInterceptor
from spakky.plugins.grpc.post_processors.add_interceptors import (
    AddInterceptorsPostProcessor,
)
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


def test_add_interceptors_skips_non_server(
    processor: AddInterceptorsPostProcessor,
) -> None:
    """Non-server Pods should be returned unchanged."""
    plain_pod = object()
    result = processor.post_process(plain_pod)
    assert result is plain_pod


def test_add_interceptors_replaces_server_with_interceptor_equipped_server(
    processor: AddInterceptorsPostProcessor,
) -> None:
    """Server Pod should be replaced with a new server that has interceptors."""
    original_server = grpc.aio.server()

    with patch(
        "spakky.plugins.grpc.post_processors.add_interceptors.grpc.aio.server"
    ) as mock_server_factory:
        new_server = MagicMock(spec=grpc.aio.Server)
        mock_server_factory.return_value = new_server

        result = processor.post_process(original_server)

        mock_server_factory.assert_called_once()
        call_kwargs = mock_server_factory.call_args
        interceptors = call_kwargs.kwargs.get(
            "interceptors", call_kwargs.args[0] if call_kwargs.args else []
        )
        assert len(interceptors) == 1
        assert isinstance(interceptors[0], ErrorHandlingInterceptor)
        assert result is new_server


def test_add_interceptors_includes_tracing_when_propagator_available(
    processor_with_tracing: AddInterceptorsPostProcessor,
) -> None:
    """Server should have both error handling and tracing interceptors when propagator exists."""
    original_server = grpc.aio.server()

    with patch(
        "spakky.plugins.grpc.post_processors.add_interceptors.grpc.aio.server"
    ) as mock_server_factory:
        new_server = MagicMock(spec=grpc.aio.Server)
        mock_server_factory.return_value = new_server

        processor_with_tracing.post_process(original_server)

        call_kwargs = mock_server_factory.call_args
        interceptors = call_kwargs.kwargs.get("interceptors", [])
        assert len(interceptors) == 2
        assert isinstance(interceptors[0], ErrorHandlingInterceptor)
        assert isinstance(interceptors[1], TracingInterceptor)
