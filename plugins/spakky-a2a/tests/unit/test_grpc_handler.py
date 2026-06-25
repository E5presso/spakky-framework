"""Unit coverage for A2A gRPC handler dispatch and envelopes."""

from collections.abc import AsyncIterator
from typing import cast

import grpc
import pytest
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.context import ServerCallContext
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    Message,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from spakky.plugins.a2a.error import (
    UnsupportedA2AGrpcEventError,
    UnsupportedA2AGrpcResultError,
)
from spakky.plugins.a2a.grpc_transport.handler import (
    A2A_GRPC_SERVICE,
    A2AGrpcHandler,
    _deserializer,
    _serializer,
    _stream_response,
)


class _CallDetails(grpc.HandlerCallDetails):
    def __init__(self, method: str) -> None:
        self.method = method
        self.invocation_metadata = ()


class _FakeRequestHandler:
    result: object
    task: Task | None

    def __init__(self, result: object | None = None, task: Task | None = None) -> None:
        self.result = result
        self.task = task

    async def on_message_send(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
    ) -> object:
        del params, context
        return self.result

    async def on_message_send_stream(
        self,
        params: SendMessageRequest,
        context: ServerCallContext,
    ) -> AsyncIterator[object]:
        del params, context
        yield self.result

    async def on_get_task(
        self,
        params: GetTaskRequest,
        context: ServerCallContext,
    ) -> Task | None:
        del params, context
        return self.task

    async def on_cancel_task(
        self,
        params: CancelTaskRequest,
        context: ServerCallContext,
    ) -> Task | None:
        del params, context
        return self.task


def _request() -> SendMessageRequest:
    return SendMessageRequest(
        message=Message(
            role=Role.ROLE_USER,
            message_id="m1",
            parts=[Part(text="hi")],
        )
    )


def _handler(
    result: object | None = None, task: Task | None = None
) -> DefaultRequestHandler:
    return cast(DefaultRequestHandler, _FakeRequestHandler(result=result, task=task))


def _context() -> grpc.aio.ServicerContext:
    return cast(grpc.aio.ServicerContext, None)


def _task(state: str = "TASK_STATE_COMPLETED") -> Task:
    return Task(id="t1", context_id="c1", status=TaskStatus(state=state))


def test_service_resolves_official_methods() -> None:
    """Official A2A gRPC paths resolve to method handlers."""
    handler = A2AGrpcHandler(_handler())

    resolved = handler.service(_CallDetails(f"/{A2A_GRPC_SERVICE}/SendMessage"))
    missing = handler.service(_CallDetails(f"/{A2A_GRPC_SERVICE}/Unknown"))

    assert resolved is not None
    assert missing is None


async def test_send_message_wraps_message_result() -> None:
    """Message-only A2A results are wrapped in SendMessageResponse.message."""
    message = Message(role=Role.ROLE_AGENT, message_id="m2", parts=[Part(text="hi")])
    handler = A2AGrpcHandler(_handler(result=message))

    response = await handler._send_message(_request(), context=_context())

    assert response.HasField("message")
    assert response.message.message_id == "m2"


async def test_send_message_rejects_unknown_result() -> None:
    """Unexpected unary results raise the A2A gRPC result error."""
    handler = A2AGrpcHandler(_handler(result=object()))

    with pytest.raises(UnsupportedA2AGrpcResultError):
        await handler._send_message(_request(), context=_context())


async def test_get_task_rejects_missing_task() -> None:
    """A missing task result is rejected before gRPC serialization."""
    handler = A2AGrpcHandler(_handler(task=None))

    with pytest.raises(UnsupportedA2AGrpcResultError):
        await handler._get_task(GetTaskRequest(id="t1"), context=_context())


async def test_cancel_task_rejects_missing_task() -> None:
    """A missing cancel result is rejected before gRPC serialization."""
    handler = A2AGrpcHandler(_handler(task=None))

    with pytest.raises(UnsupportedA2AGrpcResultError):
        await handler._cancel_task(CancelTaskRequest(id="t1"), context=_context())


async def test_streaming_method_wraps_events() -> None:
    """Streaming handler wraps each emitted A2A event."""
    handler = A2AGrpcHandler(_handler(result=_task()))
    responses = [
        response
        async for response in handler._send_streaming_message(_request(), _context())
    ]

    assert responses[0].HasField("task")


def test_stream_response_wraps_every_supported_event() -> None:
    """Task, message, status, and artifact events map to StreamResponse oneofs."""
    task = _task()
    message = Message(role=Role.ROLE_AGENT, message_id="m2", parts=[Part(text="hi")])
    status = TaskStatusUpdateEvent(
        task_id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
    )
    artifact = TaskArtifactUpdateEvent(task_id="t1", context_id="c1")

    assert _stream_response(task).HasField("task")
    assert _stream_response(message).HasField("message")
    assert _stream_response(status).HasField("status_update")
    assert _stream_response(artifact).HasField("artifact_update")


def test_stream_response_rejects_unknown_event() -> None:
    """Unsupported streaming events raise the A2A gRPC event error."""
    with pytest.raises(UnsupportedA2AGrpcEventError):
        _stream_response(
            cast(
                Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent,
                object(),
            )
        )


def test_serializer_and_deserializer_round_trip_a2a_messages() -> None:
    """A2A protobuf messages round-trip through handler wire helpers."""
    request = _request()

    decoded = _deserializer(SendMessageRequest)(_serializer(request))

    assert decoded.message.message_id == "m1"
