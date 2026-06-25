"""Integration: the AG-UI HTTP stream endpoint emits sequential chunks."""

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
from spakky.plugins.agui.http_stream import add_agui_http_stream_endpoint
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver


@Agent(spec=AgentExecutionSpec(name="http_assistant", objective="answer with a tool"))
class HttpStreamAssistant:
    """Stateless agent exercised through the HTTP streaming endpoint."""

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
    assistant = HttpStreamAssistant(_ScriptedModel())

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        runner = AgentRunner.for_agent_instance(assistant)
        return AgUiRunDriver(
            runner=runner,
            run_input=core_input,
            agent_id="http_assistant",
            projector=AgUiProjector(config),
            encoder=EventEncoder(accept=accept or ""),
        )

    add_agui_http_stream_endpoint(
        app,
        run_driver_factory=run_driver_factory,
        config=config,
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


def test_http_stream_endpoint_streams_agui_events_as_sequential_chunks() -> None:
    """POST /agui/stream이 SSE 프레이밍 없이 AG-UI event JSON chunks를 순서 전달한다."""
    client = TestClient(_build_app())

    response = client.post("/agui/stream", json=_run_agent_input())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert "data: " not in response.text
    chunks = [line for line in response.text.splitlines() if line.strip()]
    types = [loads(chunk)["type"] for chunk in chunks]
    assert types[0] == "RUN_STARTED"
    assert "TOOL_CALL_RESULT" in types
    assert types[-1] == "RUN_FINISHED"
