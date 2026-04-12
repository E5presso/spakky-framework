"""Unit tests for BindServerPostProcessor."""

import asyncio
from asyncio import Event as AsyncEvent
from unittest.mock import AsyncMock, MagicMock

import grpc.aio
import pytest
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.post_processors.bind_server import (
    BindServerPostProcessor,
    GrpcServerService,
)
from spakky.plugins.grpc.server_spec import GrpcServerSpec


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


def test_bind_server_with_non_spec_pod_expect_unchanged(
    processor: BindServerPostProcessor,
) -> None:
    """Non-spec Pods should be returned unchanged."""
    plain_pod = object()
    result = processor.post_process(plain_pod)
    assert result is plain_pod


def test_bind_server_with_spec_pod_expect_service_registered(
    processor: BindServerPostProcessor,
) -> None:
    """Spec Pod should be registered as a service in the application context."""
    spec = GrpcServerSpec()

    result = processor.post_process(spec)

    assert result is spec
    app_ctx = (
        processor._BindServerPostProcessor__application_context  # pyrefly: ignore - name-mangled private attr access
    )
    app_ctx.add_service.assert_called_once()
    service_arg = app_ctx.add_service.call_args[0][0]
    assert isinstance(service_arg, GrpcServerService)


async def test_grpc_server_service_start_async_expect_build_and_start() -> None:
    """GrpcServerService.start_async() should build and start the server."""
    spec = MagicMock(spec=GrpcServerSpec)
    built_server = MagicMock(spec=grpc.aio.Server)
    built_server.start = AsyncMock()
    spec.build = MagicMock(return_value=built_server)
    service = GrpcServerService(spec)

    await service.start_async()

    spec.build.assert_called_once()
    built_server.start.assert_awaited_once()


async def test_grpc_server_service_stop_async_without_start_expect_noop() -> None:
    """stop_async() should be a no-op when start_async() never ran."""
    spec = MagicMock(spec=GrpcServerSpec)
    service = GrpcServerService(spec)

    await service.stop_async()

    spec.build.assert_not_called()


async def test_grpc_server_service_stop_async_after_start_expect_graceful_stop() -> (
    None
):
    """stop_async() should stop the underlying server with grace."""
    spec = MagicMock(spec=GrpcServerSpec)
    built_server = MagicMock(spec=grpc.aio.Server)
    built_server.start = AsyncMock()
    built_server.stop = AsyncMock()
    spec.build = MagicMock(return_value=built_server)
    service = GrpcServerService(spec)
    await service.start_async()

    await service.stop_async()

    built_server.stop.assert_awaited_once_with(grace=5.0)


def test_grpc_server_service_set_stop_event_expect_stored() -> None:
    """GrpcServerService should accept a stop event."""
    spec = MagicMock(spec=GrpcServerSpec)
    service = GrpcServerService(spec)
    event = asyncio.Event()

    service.set_stop_event(event)

    assert service._stop_event is event
