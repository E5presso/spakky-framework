"""Integration: the AG-UI SSE endpoint streams a well-formed event stream."""

from collections.abc import AsyncIterator
from json import loads
from typing import override

from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentRunner,
    EvidenceCapture,
    Idempotency,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
    ModelToolCall,
    RunAgentInput,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.interfaces.model import IAgentModel

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import add_agui_endpoint
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver


@Agent(spec=AgentExecutionSpec(name="sse_assistant", objective="answer with a tool"))
class SseAssistant:
    """Stateless agent exercised through the SSE endpoint."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model

    @agent_tool(
        schema_name="lookup",
        description="Look up a fact.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        evidence=EvidenceCapture.STRUCTURED,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def lookup(self, topic: str) -> str:
        """Look up a topic."""
        return f"fact:{topic}"


class _ScriptedModel(IAgentModel):
    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA, token_delta="hello"
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="lookup", arguments={"topic": "agents"}, call_id="call-1"
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


def _build_app() -> FastAPI:
    app = FastAPI()
    config = AgUiConfig()
    assistant = SseAssistant(_ScriptedModel())

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        runner = AgentRunner.for_agent_instance(assistant)
        return AgUiRunDriver(
            runner=runner,
            run_input=core_input,
            agent_id="sse_assistant",
            projector=AgUiProjector(config),
            encoder=EventEncoder(accept=accept or ""),
        )

    add_agui_endpoint(app, run_driver_factory=run_driver_factory, config=config)
    return app


def _run_agent_input() -> dict[str, object]:
    return {
        "threadId": "conv-1",
        "runId": "run-1",
        "state": None,
        "messages": [{"id": "u1", "role": "user", "content": "look up agents"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }


def test_sse_endpoint_streams_event_stream_frames_in_order() -> None:
    """POST /agui가 순서가 보존된 valid SSE 프레임의 text/event-stream을 반환한다."""
    client = TestClient(_build_app())

    response = client.post("/agui", json=_run_agent_input())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [line for line in response.text.split("\n\n") if line.startswith("data: ")]
    types = [loads(frame.removeprefix("data: ").strip())["type"] for frame in frames]
    assert types[0] == "RUN_STARTED"
    assert "TOOL_CALL_RESULT" in types
    assert types[-1] == "RUN_FINISHED"


def test_sse_endpoint_rejects_missing_user_message() -> None:
    """user 메시지가 없는 입력은 AgUiRunResolutionError로 거부된다."""
    client = TestClient(_build_app(), raise_server_exceptions=True)
    payload = _run_agent_input()
    payload["messages"] = []

    from spakky.plugins.agui.error import AgUiRunResolutionError
    from pytest import raises

    with raises(AgUiRunResolutionError):
        client.post("/agui", json=payload)
