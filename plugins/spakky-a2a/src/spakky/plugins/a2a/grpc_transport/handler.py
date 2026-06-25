"""Official A2A gRPC service handler backed by the existing A2A executor.

The a2a-sdk ships protobuf descriptors for ``lf.a2a.v1.A2AService``. This
handler binds those official method names to the same ``DefaultRequestHandler``
used by the JSON-RPC transport, so AgentCard derivation, task persistence,
executor adaptation, and neutral agent-event projection remain shared.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import grpc
from a2a.server.context import ServerCallContext
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    Message,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from google.protobuf.message import Message as ProtobufMessage
from typing import override

from spakky.plugins.a2a.error import (
    UnsupportedA2AGrpcEventError,
    UnsupportedA2AGrpcResultError,
)

A2A_GRPC_SERVICE = "lf.a2a.v1.A2AService"
"""Fully qualified official A2A gRPC service name from the a2a-sdk descriptor."""


class A2AGrpcHandler(grpc.GenericRpcHandler):
    """Generic gRPC handler for the official A2A service methods."""

    _handler: DefaultRequestHandler
    _handlers: dict[str, grpc.RpcMethodHandler]

    def __init__(self, handler: DefaultRequestHandler) -> None:
        self._handler = handler
        self._handlers = {
            self._method("SendMessage"): grpc.unary_unary_rpc_method_handler(
                self._send_message,
                request_deserializer=_deserializer(SendMessageRequest),
                response_serializer=_serializer,
            ),
            self._method("SendStreamingMessage"): grpc.unary_stream_rpc_method_handler(
                self._send_streaming_message,
                request_deserializer=_deserializer(SendMessageRequest),
                response_serializer=_serializer,
            ),
            self._method("GetTask"): grpc.unary_unary_rpc_method_handler(
                self._get_task,
                request_deserializer=_deserializer(GetTaskRequest),
                response_serializer=_serializer,
            ),
            self._method("CancelTask"): grpc.unary_unary_rpc_method_handler(
                self._cancel_task,
                request_deserializer=_deserializer(CancelTaskRequest),
                response_serializer=_serializer,
            ),
        }

    @override
    def service(
        self,
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler | None:
        """Return the method handler for an official A2A gRPC path."""
        return self._handlers.get(handler_call_details.method)

    @staticmethod
    def _method(name: str) -> str:
        """Return the fully qualified gRPC method path for an A2A method."""
        return f"/{A2A_GRPC_SERVICE}/{name}"

    async def _send_message(
        self,
        request: SendMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> SendMessageResponse:
        del context
        result = await self._handler.on_message_send(request, ServerCallContext())
        if isinstance(result, Task):
            return SendMessageResponse(task=result)
        if isinstance(result, Message):
            return SendMessageResponse(message=result)
        raise UnsupportedA2AGrpcResultError(type(result))

    async def _send_streaming_message(
        self,
        request: SendMessageRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[StreamResponse]:
        del context
        async for event in self._handler.on_message_send_stream(
            request, ServerCallContext()
        ):
            yield _stream_response(event)

    async def _get_task(
        self,
        request: GetTaskRequest,
        context: grpc.aio.ServicerContext,
    ) -> Task:
        del context
        task = await self._handler.on_get_task(request, ServerCallContext())
        if task is None:
            raise UnsupportedA2AGrpcResultError(type(task))
        return task

    async def _cancel_task(
        self,
        request: CancelTaskRequest,
        context: grpc.aio.ServicerContext,
    ) -> Task:
        del context
        task = await self._handler.on_cancel_task(request, ServerCallContext())
        if task is None:
            raise UnsupportedA2AGrpcResultError(type(task))
        return task


def _deserializer[MessageT: ProtobufMessage](
    message_type: type[MessageT],
) -> Callable[[bytes], MessageT]:
    """Build a protobuf bytes deserializer for an A2A SDK message class."""

    def _deserialize(data: bytes) -> MessageT:
        message = message_type()
        message.ParseFromString(data)
        return message

    return _deserialize


def _serializer(message: ProtobufMessage) -> bytes:
    """Serialize an A2A SDK protobuf message."""
    return message.SerializeToString()


def _stream_response(
    event: Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent,
) -> StreamResponse:
    """Wrap an A2A task event in the official streaming response envelope."""
    if isinstance(event, Task):
        return StreamResponse(task=event)
    if isinstance(event, Message):
        return StreamResponse(message=event)
    if isinstance(event, TaskStatusUpdateEvent):
        return StreamResponse(status_update=event)
    if isinstance(event, TaskArtifactUpdateEvent):
        return StreamResponse(artifact_update=event)
    raise UnsupportedA2AGrpcEventError(type(event))
