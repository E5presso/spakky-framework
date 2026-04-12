"""Unit tests for BindServerPostProcessor."""

from asyncio import Event as AsyncEvent
from dataclasses import dataclass
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


@dataclass
class BindServerHarness:
    """Bundle of processor + observable collaborators for behavior assertions."""

    processor: BindServerPostProcessor
    application_context: MagicMock
    container: MagicMock
    task_stop_event: AsyncEvent


@pytest.fixture
def harness() -> BindServerHarness:
    """Create a BindServerPostProcessor wired to observable mock collaborators."""
    proc = BindServerPostProcessor.__new__(BindServerPostProcessor)
    container = MagicMock(spec=IContainer)
    application_context = MagicMock(spec=IApplicationContext)
    task_stop_event = AsyncEvent()
    application_context.task_stop_event = task_stop_event
    proc.set_container(container)
    proc.set_application_context(application_context)
    return BindServerHarness(
        processor=proc,
        application_context=application_context,
        container=container,
        task_stop_event=task_stop_event,
    )


def test_bind_server_with_non_spec_pod_expect_pod_returned_and_no_service_registered(
    harness: BindServerHarness,
) -> None:
    """Non-spec Pods should pass through without touching the application context."""
    plain_pod = object()

    result = harness.processor.post_process(plain_pod)

    assert result is plain_pod
    harness.application_context.add_service.assert_not_called()


async def test_bind_server_with_spec_pod_expect_service_wrapping_spec_added_to_context(
    harness: BindServerHarness,
) -> None:
    """Spec Pod should yield a GrpcServerService that builds the same spec on start."""
    built_server = MagicMock(spec=grpc.aio.Server)
    built_server.start = AsyncMock()
    spec = MagicMock(spec=GrpcServerSpec)
    spec.build = MagicMock(return_value=built_server)

    result = harness.processor.post_process(spec)

    assert result is spec
    harness.application_context.add_service.assert_called_once()
    (service_arg,) = harness.application_context.add_service.call_args[0]
    assert isinstance(service_arg, GrpcServerService)

    # Observable behavior: the registered service, when started, drives
    # the exact spec we passed in — proving the processor wrapped it
    # correctly without inspecting private attributes.
    await service_arg.start_async()
    spec.build.assert_called_once()
    built_server.start.assert_awaited_once()


async def test_grpc_server_service_start_async_expect_build_and_start() -> None:
    """GrpcServerService.start_async() should build the spec and start the server."""
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
    """stop_async() should stop the underlying server with the configured grace."""
    spec = MagicMock(spec=GrpcServerSpec)
    built_server = MagicMock(spec=grpc.aio.Server)
    built_server.start = AsyncMock()
    built_server.stop = AsyncMock()
    spec.build = MagicMock(return_value=built_server)
    service = GrpcServerService(spec)
    await service.start_async()

    await service.stop_async()

    built_server.stop.assert_awaited_once_with(grace=5.0)


async def test_grpc_server_service_stop_async_twice_expect_single_graceful_stop() -> (
    None
):
    """Calling stop_async() twice should stop the server only once."""
    spec = MagicMock(spec=GrpcServerSpec)
    built_server = MagicMock(spec=grpc.aio.Server)
    built_server.start = AsyncMock()
    built_server.stop = AsyncMock()
    spec.build = MagicMock(return_value=built_server)
    service = GrpcServerService(spec)
    await service.start_async()

    await service.stop_async()
    await service.stop_async()

    built_server.stop.assert_awaited_once_with(grace=5.0)
