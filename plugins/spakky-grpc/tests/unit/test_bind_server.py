"""Unit tests for BindServerPostProcessor."""

from asyncio import Event as AsyncEvent
from unittest.mock import MagicMock

import grpc.aio
import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.post_processors.bind_server import (
    BindServerPostProcessor,
    GrpcServerService,
)


@pytest.fixture
def processor() -> BindServerPostProcessor:
    """Create a configured BindServerPostProcessor."""
    proc = BindServerPostProcessor.__new__(BindServerPostProcessor)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    application_context.task_stop_event = AsyncEvent()
    proc.set_container(container)
    proc.set_application_context(application_context)
    return proc


def test_bind_server_skips_non_server(
    processor: BindServerPostProcessor,
) -> None:
    """Non-server Pods should be returned unchanged."""
    plain_pod = object()
    result = processor.post_process(plain_pod)
    assert result is plain_pod


def test_bind_server_registers_service_for_server_pod(
    processor: BindServerPostProcessor,
) -> None:
    """Server Pod should be registered as a service in the application context."""
    server = MagicMock(spec=grpc.aio.Server)

    result = processor.post_process(server)

    assert result is server
    app_ctx = (
        processor._BindServerPostProcessor__application_context  # pyrefly: ignore - name-mangled private attr access
    )
    app_ctx.add_service.assert_called_once()
    service_arg = app_ctx.add_service.call_args[0][0]
    assert isinstance(service_arg, GrpcServerService)


async def test_grpc_server_service_start_calls_server_start() -> None:
    """GrpcServerService.start_async() should start the underlying server."""
    server = MagicMock(spec=grpc.aio.Server)
    server.start = MagicMock(return_value=_coro(None))
    service = GrpcServerService(server)

    await service.start_async()

    server.start.assert_called_once()


async def test_grpc_server_service_stop_calls_server_stop() -> None:
    """GrpcServerService.stop_async() should stop the underlying server with grace."""
    server = MagicMock(spec=grpc.aio.Server)
    server.stop = MagicMock(return_value=_coro(None))
    service = GrpcServerService(server)

    await service.stop_async()

    server.stop.assert_called_once_with(grace=5.0)


def test_grpc_server_service_set_stop_event() -> None:
    """GrpcServerService should accept a stop event."""
    import asyncio

    server = MagicMock(spec=grpc.aio.Server)
    service = GrpcServerService(server)
    event = asyncio.Event()

    service.set_stop_event(event)

    assert service._stop_event is event


async def _coro(value: object) -> object:
    """Helper to create a simple coroutine returning a value."""
    return value
