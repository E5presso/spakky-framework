"""Integration: @AgUiAgent is mounted on FastAPI through DI post-processing."""

from collections.abc import AsyncIterator
from json import loads
from typing import override

from fastapi import FastAPI
from fastapi.testclient import TestClient
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    IAgentModel,
    ModelCapability,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelStreamEventKind,
)
from spakky.agent.main import initialize as initialize_agent
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.agui.main import initialize as initialize_agui
from spakky.plugins.agui.stereotypes.agui_agent import AgUiAgent


@Pod()
class AutoMountModel(IAgentModel):
    """Model double returning a single token and DONE."""

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
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="hello",
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@AgUiAgent()
@Agent(spec=AgentExecutionSpec(name="auto_agui", objective="answer"))
class AutoMountedAssistant:
    """Agent exposed through AG-UI solely by declaration."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Pod(name="fastapi_app")
def fastapi_app() -> FastAPI:
    """Provide a FastAPI host Pod for the AG-UI post-processor."""
    return FastAPI()


def _run_agent_input() -> dict[str, object]:
    return {
        "threadId": "conv-1",
        "runId": "run-1",
        "state": None,
        "messages": [{"id": "u1", "role": "user", "content": "say hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }


def _build_app() -> FastAPI:
    app = SpakkyApplication(ApplicationContext())
    initialize_agent(app)
    initialize_agui(app)
    app.add(fastapi_app)
    app.add(AutoMountModel)
    app.add(AutoMountedAssistant)
    app.start()
    return app.container.get(FastAPI)


def test_agui_agent_mounts_sse_endpoint_without_manual_factory() -> None:
    """@AgUiAgent @Agent가 수동 endpoint helper 없이 /agui SSE를 노출한다."""
    client = TestClient(_build_app())

    response = client.post("/agui", json=_run_agent_input())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [line for line in response.text.split("\n\n") if line.startswith("data: ")]
    types = [loads(frame.removeprefix("data: ").strip())["type"] for frame in frames]
    assert types[0] == "RUN_STARTED"
    assert "TEXT_MESSAGE_CONTENT" in types
    assert types[-1] == "RUN_FINISHED"
