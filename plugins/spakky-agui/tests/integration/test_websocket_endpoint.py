"""Integration: the AG-UI WebSocket endpoint streams encoded event frames."""

from collections.abc import AsyncIterator
from json import loads
from typing import cast, override

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
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver
from spakky.plugins.agui.websocket import add_agui_websocket_endpoint


@Agent(spec=AgentExecutionSpec(name="ws_assistant", objective="answer with a tool"))
class WebSocketAssistant:
    """Stateless agent exercised through the WebSocket endpoint."""

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


class _StaticDriver:
    async def __aiter__(self) -> AsyncIterator[str]:
        yield 'data: {"type":"RUN_FINISHED"}\n\n'


def _build_runner_app() -> FastAPI:
    app = FastAPI()
    config = AgUiConfig()
    assistant = WebSocketAssistant(_ScriptedModel())

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        runner = AgentRunner.for_agent_instance(assistant)
        return AgUiRunDriver(
            runner=runner,
            run_input=core_input,
            agent_id="ws_assistant",
            projector=AgUiProjector(config),
            encoder=EventEncoder(accept=accept or ""),
        )

    add_agui_websocket_endpoint(
        app, run_driver_factory=run_driver_factory, config=config
    )
    return app


def _build_capture_app(
    captured: list[tuple[RunAgentInput, AgUiRunAgentInput, str | None]],
) -> FastAPI:
    app = FastAPI()

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        captured.append((core_input, ag_ui_input, accept))
        return cast(AgUiRunDriver, _StaticDriver())

    add_agui_websocket_endpoint(
        app,
        run_driver_factory=run_driver_factory,
        config=AgUiConfig(),
    )
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


def _resume_input() -> dict[str, object]:
    payload = _run_agent_input()
    payload["forwardedProps"] = {
        "approvalDecision": {
            "request_id": "approval:run-1:note.write",
            "decision": "approve",
        }
    }
    return payload


def _event_type(frame: str) -> str:
    return str(loads(frame.removeprefix("data: ").strip())["type"])


def _receive_until_finished(client: TestClient) -> list[str]:
    frames: list[str] = []
    with client.websocket_connect("/agui/ws") as websocket:
        websocket.send_json(_run_agent_input())
        while True:
            frame = websocket.receive_text()
            frames.append(frame)
            if _event_type(frame) == "RUN_FINISHED":
                return frames


def test_websocket_endpoint_streams_encoded_frames_in_order() -> None:
    """WS /agui/ws가 AG-UI encoded frame을 순서대로 text message로 스트리밍한다."""
    frames = _receive_until_finished(TestClient(_build_runner_app()))

    types = [_event_type(frame) for frame in frames]
    assert types[0] == "RUN_STARTED"
    assert "TOOL_CALL_RESULT" in types
    assert types[-1] == "RUN_FINISHED"


def test_websocket_endpoint_accepts_followup_run_input_on_same_connection() -> None:
    """같은 WS 연결에서 다음 RunAgentInput을 받아 resume approval을 매핑한다."""
    captured: list[tuple[RunAgentInput, AgUiRunAgentInput, str | None]] = []
    client = TestClient(_build_capture_app(captured))

    with client.websocket_connect(
        "/agui/ws", headers={"accept": "text/event-stream"}
    ) as websocket:
        websocket.send_json(_run_agent_input())
        assert _event_type(websocket.receive_text()) == "RUN_FINISHED"
        websocket.send_json(_resume_input())
        assert _event_type(websocket.receive_text()) == "RUN_FINISHED"

    assert captured[0][0].resume is False
    assert captured[1][0].resume is True
    assert captured[1][1].forwarded_props is not None
    assert captured[1][2] == "text/event-stream"
