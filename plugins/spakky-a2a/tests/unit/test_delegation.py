"""Tests for A2A teammate delegation client event mapping."""

from collections.abc import AsyncGenerator, Mapping
from typing import cast

import httpx
import pytest
from a2a.client import ClientFactory
from a2a.types import (
    AgentCard,
    Artifact,
    Message,
    Part,
    Role,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from google.protobuf.json_format import ParseDict
from google.protobuf.struct_pb2 import Value
from spakky.agent import (
    AgentDelegateTarget,
    ArtifactEvent,
    AgentYieldKind,
    MessageDeltaEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepStartedEvent,
)
from spakky.agent.delegation import DelegationPacket
from spakky.agent.error import AgentToolDispatchError

from spakky.plugins.a2a.client import A2ARemoteAgentClient, RemoteA2AMessage
from spakky.plugins.a2a.delegation import A2AAgentDelegate, A2AStreamEventMapper


def _packet() -> DelegationPacket:
    return DelegationPacket(
        id="parent-run:delegate-1",
        parent_agent_state_id="parent-run",
        target=AgentDelegateTarget(
            agent_type="remote:researcher",
            agent_name="researcher",
            metadata={"card_url": "https://agents.example.com/card.json"},
        ),
        task={"instruction": "inspect"},
        metadata={"conversation_id": "thread-1"},
    )


def test_stream_mapper_expect_status_updates_keep_parent_attribution() -> None:
    """A2A status update가 parent linkage를 가진 neutral event로 매핑된다."""
    response = StreamResponse(
        status_update=TaskStatusUpdateEvent(
            task_id="child-task",
            context_id="thread-1",
            status=TaskStatus(
                state=TaskState.TASK_STATE_WORKING,
                message=Message(
                    role=Role.ROLE_AGENT,
                    message_id="m1",
                    parts=[Part(text="working")],
                ),
            ),
        )
    )

    events = A2AStreamEventMapper().map(response, _packet())

    assert isinstance(events[0], StepStartedEvent)
    assert isinstance(events[1], MessageDeltaEvent)
    assert events[1].delta == "working"
    assert events[1].attribution.agent_id == "researcher"
    assert events[1].attribution.run_id == "child-task"
    assert events[1].attribution.parent_run_id == "parent-run"
    assert events[1].attribution.conversation_id == "thread-1"


def test_stream_mapper_expect_maps_terminal_and_artifact_events() -> None:
    """A2A task/artifact update가 neutral terminal/artifact event로 매핑된다."""
    value = Value()
    ParseDict({"answer": 42}, value)
    mapper = A2AStreamEventMapper()
    packet = _packet()

    completed = mapper.map(
        StreamResponse(
            task=Task(
                id="child-task",
                context_id="thread-1",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        ),
        packet,
    )
    failed = mapper.map(
        StreamResponse(
            status_update=TaskStatusUpdateEvent(
                task_id="child-task",
                context_id="thread-1",
                status=TaskStatus(state=TaskState.TASK_STATE_FAILED),
            )
        ),
        packet,
    )
    artifact = mapper.map(
        StreamResponse(
            artifact_update=TaskArtifactUpdateEvent(
                task_id="child-task",
                context_id="thread-1",
                artifact=Artifact(
                    artifact_id="artifact-1",
                    name="report",
                    parts=[
                        Part(text="text"),
                        Part(data=value),
                        Part(url="https://example.com/report"),
                        Part(raw=b"raw"),
                        Part(),
                    ],
                ),
            )
        ),
        packet,
    )

    assert isinstance(completed[0], RunStartedEvent)
    assert isinstance(completed[1], RunFinishedEvent)
    assert isinstance(failed[0], RunFinishedEvent)
    assert failed[0].error == {
        "code": "remote_a2a_failed",
        "message": "TASK_STATE_FAILED",
    }
    assert isinstance(artifact[0], ArtifactEvent)
    assert artifact[0].content == [
        "text",
        {"answer": 42.0},
        {"url": "https://example.com/report"},
        {"raw": "726177"},
        {},
    ]


def test_stream_mapper_expect_failed_task_carries_remote_failure_error() -> None:
    """terminal Task가 failed 상태면 RunFinished가 remote 실패 error를 싣는다."""
    events = A2AStreamEventMapper().map(
        StreamResponse(
            task=Task(
                id="child-task",
                context_id="thread-1",
                status=TaskStatus(state=TaskState.TASK_STATE_FAILED),
            )
        ),
        _packet(),
    )

    assert isinstance(events[0], RunStartedEvent)
    finished = events[1]
    assert isinstance(finished, RunFinishedEvent)
    assert finished.error == {
        "code": "remote_a2a_failed",
        "message": "TASK_STATE_FAILED",
    }
    assert finished.attribution.run_id == "child-task"


def test_stream_mapper_expect_ignores_empty_message_and_unknown_response() -> None:
    """본문 없는 message와 payload 없는 response는 이벤트를 만들지 않는다."""
    mapper = A2AStreamEventMapper()

    empty_message = mapper.map(
        StreamResponse(
            message=Message(
                role=Role.ROLE_AGENT,
                message_id="m1",
                task_id="child-task",
                context_id="thread-1",
            )
        ),
        _packet(),
    )

    assert empty_message == ()
    assert mapper.map(StreamResponse(), _packet()) == ()


async def test_a2a_delegate_expect_streams_remote_message_and_final_task() -> None:
    """A2A delegate가 remote stream을 DelegationToolResult로 수집한다."""
    fake_client = _FakeRemoteClient(
        (
            StreamResponse(
                message=Message(
                    role=Role.ROLE_AGENT,
                    message_id="m1",
                    task_id="child-task",
                    context_id="thread-1",
                    parts=[Part(text="done")],
                )
            ),
            StreamResponse(
                task=Task(
                    id="child-task",
                    context_id="thread-1",
                    status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                )
            ),
        )
    )

    result = await A2AAgentDelegate(
        client=cast(A2ARemoteAgentClient, fake_client)
    ).delegate_tool_result(_packet())

    assert (
        result.summary
        == "remote teammate 'researcher' finished with TASK_STATE_COMPLETED"
    )
    assert isinstance(result.output, Mapping)
    assert result.output["task_id"] == "child-task"
    assert any(isinstance(event, MessageDeltaEvent) for event in result.events)
    assert any(isinstance(event, RunFinishedEvent) for event in result.events)
    assert fake_client.last_message is not None
    assert fake_client.last_message.text == "inspect"


async def test_a2a_delegate_expect_delegate_yields_terminal_result() -> None:
    """delegate() 호환 경로가 AgentYield terminal result를 방출한다."""
    fake_client = _FakeRemoteClient(
        (
            StreamResponse(
                task=Task(
                    id="child-task",
                    context_id="thread-1",
                    status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
                )
            ),
        )
    )

    items = [
        item
        async for item in A2AAgentDelegate(
            client=cast(A2ARemoteAgentClient, fake_client)
        ).delegate(_packet())
    ]

    assert len(items) == 1
    assert items[0].kind == AgentYieldKind.FINAL
    assert items[0].payload.packet_id == "parent-run:delegate-1"


async def test_a2a_delegate_expect_unknown_output_when_remote_returns_no_task() -> None:
    """remote stream에 task/status가 없으면 unknown output으로 수렴한다."""
    result = await A2AAgentDelegate(
        client=cast(A2ARemoteAgentClient, _FakeRemoteClient((StreamResponse(),)))
    ).delegate_tool_result(_packet())

    assert result.output == {"task_id": None, "state": "unknown"}


async def test_a2a_delegate_expect_rejects_missing_card_url_and_instruction() -> None:
    """remote delegate 입력에 card_url과 instruction이 없으면 custom error다."""
    delegate = A2AAgentDelegate(
        client=cast(A2ARemoteAgentClient, _FakeRemoteClient(()))
    )

    bad_target = DelegationPacket(
        id="parent-run:delegate-1",
        parent_agent_state_id="parent-run",
        target=AgentDelegateTarget(agent_type="remote:researcher"),
        task={"instruction": "inspect"},
    )
    bad_instruction = DelegationPacket(
        id="parent-run:delegate-1",
        parent_agent_state_id="parent-run",
        target=_packet().target,
        task={},
    )

    with pytest.raises(AgentToolDispatchError):
        await delegate.delegate_tool_result(bad_target)
    with pytest.raises(AgentToolDispatchError):
        await delegate.delegate_tool_result(bad_instruction)


async def test_remote_client_collects_stream_and_fetches_task() -> None:
    """A2A client wrapper가 stream 수집과 task fetch에 SDK client를 사용한다."""
    sdk_client = _FakeSdkClient()
    client = _FakeFactoryClient(sdk_client)

    sent = await client.send_message(
        "https://agents.example.com/card.json",
        RemoteA2AMessage(text="hi"),
    )
    task = await client.get_task("https://agents.example.com/card.json", "task-1")

    assert len(sent) == 1
    assert task.id == "task-1"
    assert sdk_client.closed_count == 2


async def test_remote_client_http_client_expect_supports_owned_and_borrowed() -> None:
    """httpx client context manager가 borrowed와 owned 모드를 모두 지원한다."""
    borrowed = httpx.AsyncClient()
    try:
        async with A2ARemoteAgentClient(httpx_client=borrowed)._http_client() as client:
            assert client is borrowed
    finally:
        await borrowed.aclose()

    async with A2ARemoteAgentClient()._http_client() as owned:
        assert isinstance(owned, httpx.AsyncClient)


class _FakeRemoteClient:
    """Network-free A2A client test double."""

    _events: tuple[StreamResponse, ...]
    last_message: RemoteA2AMessage | None

    def __init__(self, events: tuple[StreamResponse, ...]) -> None:
        self._events = events
        self.last_message = None

    async def stream_message(
        self,
        card_url: str,
        message: RemoteA2AMessage,
    ) -> AsyncGenerator[StreamResponse, None]:
        self.last_message = message
        for event in self._events:
            yield event


class _FakeSdkClient:
    """SDK client fake returned by the ClientFactory test double."""

    closed_count: int

    def __init__(self) -> None:
        self.closed_count = 0

    async def send_message(
        self,
        request: object,
    ) -> AsyncGenerator[StreamResponse, None]:
        yield StreamResponse(
            task=Task(
                id="task-1",
                context_id="thread-1",
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        )

    async def get_task(self, request: object) -> Task:
        return Task(
            id="task-1",
            context_id="thread-1",
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
        )

    async def close(self) -> None:
        self.closed_count += 1


class _FakeFactory:
    """ClientFactory fake that returns a prebuilt SDK client."""

    _client: _FakeSdkClient

    def __init__(self, client: _FakeSdkClient) -> None:
        self._client = client

    def create(self, card: AgentCard) -> _FakeSdkClient:
        return self._client


class _FakeFactoryClient(A2ARemoteAgentClient):
    """A2A client wrapper test double avoiding network AgentCard resolution."""

    def __init__(self, sdk_client: _FakeSdkClient) -> None:
        super().__init__()
        self._factory = cast(ClientFactory, _FakeFactory(sdk_client))

    async def resolve_card(self, card_url: str) -> AgentCard:
        return AgentCard(name="remote", description="remote", version="1.0.0")
