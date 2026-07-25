"""End-to-end A2A gRPC transport tests over the official service descriptor."""

from collections.abc import AsyncIterator, Callable, Sequence

import grpc.aio
import pytest
import pytest_asyncio
from a2a.types import (
    CancelTaskRequest,
    GetTaskRequest,
    Message,
    Part,
    Role,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    Task,
    TaskState,
)
from google.protobuf.message import Message as ProtobufMessage
from spakky.agent.interfaces.model import ModelStreamEvent
from spakky.plugins.grpc.server_spec import GrpcServerSpec

from spakky.plugins.a2a.grpc_transport.builder import build_a2a_grpc_handler
from spakky.plugins.a2a.grpc_transport.handler import A2A_GRPC_SERVICE
from tests.integration.conftest import (
    AssistantAgent,
    ScriptedModel,
)
from tests.unit.conftest import (
    FakeEvidenceRepository,
    FakeSignalRepository,
    FakeStateRepository,
)

type MessageDeserializer[MessageT: ProtobufMessage] = Callable[[bytes], MessageT]


def _serialize(message: ProtobufMessage) -> bytes:
    return message.SerializeToString()


def _deserialize[MessageT: ProtobufMessage](
    message_type: type[MessageT],
) -> MessageDeserializer[MessageT]:
    def _inner(data: bytes) -> MessageT:
        message = message_type()
        message.ParseFromString(data)
        return message

    return _inner


def _method(name: str) -> str:
    return f"/{A2A_GRPC_SERVICE}/{name}"


def _message(text: str, message_id: str = "m1") -> Message:
    return Message(
        role=Role.ROLE_USER,
        message_id=message_id,
        parts=[Part(text=text)],
    )


def _agent(events: Sequence[ModelStreamEvent]) -> AssistantAgent:
    return AssistantAgent(
        ScriptedModel(events),
        FakeStateRepository(),
        FakeSignalRepository(),
        FakeEvidenceRepository(),
    )


@pytest_asyncio.fixture(name="grpc_channel")
async def get_grpc_channel_fixture(
    token_events: Sequence[ModelStreamEvent],
) -> AsyncIterator[grpc.aio.Channel]:
    """Boot a real gRPC server exposing the official A2A service."""
    spec = GrpcServerSpec()
    spec.add_insecure_port("127.0.0.1:0")
    spec.add_handler(
        build_a2a_grpc_handler(
            _agent(token_events),
            base_url="grpc://assistant.local",
            version="1.0.0",
        )
    )
    server = await spec.build_async()
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{spec.bound_ports[0]}")
    try:
        yield channel
    finally:
        await channel.close()
        await server.stop(grace=0)


@pytest_asyncio.fixture(name="approval_grpc_channel")
async def get_approval_grpc_channel_fixture(
    approval_events: Sequence[ModelStreamEvent],
) -> AsyncIterator[grpc.aio.Channel]:
    """Boot a gRPC server whose scripted agent pauses for approval."""
    spec = GrpcServerSpec()
    spec.add_insecure_port("127.0.0.1:0")
    spec.add_handler(
        build_a2a_grpc_handler(
            _agent(approval_events),
            base_url="grpc://assistant.local",
            version="1.0.0",
        )
    )
    server = await spec.build_async()
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{spec.bound_ports[0]}")
    try:
        yield channel
    finally:
        await channel.close()
        await server.stop(grace=0)


@pytest.mark.integration
async def test_send_message_runs_agent_to_completion_over_grpc(
    grpc_channel: grpc.aio.Channel,
) -> None:
    """SendMessage returns a completed A2A task over the official gRPC method."""
    call = grpc_channel.unary_unary(
        _method("SendMessage"),
        request_serializer=_serialize,
        response_deserializer=_deserialize(SendMessageResponse),
    )

    response = await call(SendMessageRequest(message=_message("hi")))

    assert response.HasField("task")
    assert response.task.status.state == TaskState.TASK_STATE_COMPLETED
    history_text = "".join(
        part.text
        for message in response.task.history
        for part in message.parts
        if part.HasField("text")
    )
    assert "hello " in history_text and "world" in history_text


@pytest.mark.integration
async def test_send_streaming_message_emits_task_lifecycle_over_grpc(
    grpc_channel: grpc.aio.Channel,
) -> None:
    """SendStreamingMessage yields submitted, working, and completed updates."""
    call = grpc_channel.unary_stream(
        _method("SendStreamingMessage"),
        request_serializer=_serialize,
        response_deserializer=_deserialize(StreamResponse),
    )

    states: list[TaskState.ValueType] = []
    async for response in call(SendMessageRequest(message=_message("hi"))):
        if response.HasField("task"):
            states.append(response.task.status.state)
        if response.HasField("status_update"):
            states.append(response.status_update.status.state)

    assert states[0] == TaskState.TASK_STATE_SUBMITTED
    assert TaskState.TASK_STATE_WORKING in states
    assert states[-1] == TaskState.TASK_STATE_COMPLETED


@pytest.mark.integration
async def test_get_task_returns_persisted_task_over_grpc(
    grpc_channel: grpc.aio.Channel,
) -> None:
    """GetTask returns the task persisted by a previous SendMessage call."""
    send = grpc_channel.unary_unary(
        _method("SendMessage"),
        request_serializer=_serialize,
        response_deserializer=_deserialize(SendMessageResponse),
    )
    get = grpc_channel.unary_unary(
        _method("GetTask"),
        request_serializer=_serialize,
        response_deserializer=_deserialize(Task),
    )
    sent = await send(SendMessageRequest(message=_message("hi")))

    task = await get(GetTaskRequest(id=sent.task.id))

    assert task.id == sent.task.id
    assert task.status.state == TaskState.TASK_STATE_COMPLETED


@pytest.mark.integration
async def test_cancel_task_marks_input_required_task_canceled_over_grpc(
    approval_grpc_channel: grpc.aio.Channel,
) -> None:
    """CancelTask appends the cancel signal and returns a canceled task."""
    send = approval_grpc_channel.unary_unary(
        _method("SendMessage"),
        request_serializer=_serialize,
        response_deserializer=_deserialize(SendMessageResponse),
    )
    cancel = approval_grpc_channel.unary_unary(
        _method("CancelTask"),
        request_serializer=_serialize,
        response_deserializer=_deserialize(Task),
    )
    paused = await send(SendMessageRequest(message=_message("write")))

    canceled = await cancel(CancelTaskRequest(id=paused.task.id))

    assert paused.task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED
    assert canceled.status.state == TaskState.TASK_STATE_CANCELED
