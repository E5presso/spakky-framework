"""Integration: @A2AAgentServer agents mount on ASGI hosts through DI."""

from collections.abc import AsyncIterator

import httpx
from a2a.utils import DEFAULT_RPC_URL
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
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.pod import Pod
from starlette.applications import Starlette
from typing import override

from spakky.plugins.a2a.main import initialize as initialize_a2a
from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer

type JsonObject = dict[str, object]


@Pod()
class AutoMountModel(IAgentModel):
    """Model double returning one streamed token."""

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


@A2AAgentServer(base_url="http://auto.local", version="1.0.0")
@Agent(spec=AgentExecutionSpec(name="auto_a2a", objective="answer"))
class AutoMountedA2AAgent:
    """Agent exposed as A2A solely by declaration."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Pod(name="asgi_host")
def asgi_host() -> Starlette:
    """Provide a Starlette host Pod for the A2A mount post-processor."""
    return Starlette()


def _send(method: str, params: JsonObject) -> JsonObject:
    return {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}


def _user_message(text: str) -> JsonObject:
    return {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": "m1",
        }
    }


def _build_app() -> Starlette:
    app = SpakkyApplication(ApplicationContext())
    initialize_a2a(app)
    app.add(asgi_host)
    app.add(AutoMountModel)
    app.add(AutoMountedA2AAgent)
    app.start()
    return app.container.get(Starlette)


async def test_a2a_agent_mounts_jsonrpc_app_without_manual_builder() -> None:
    """@A2AAgentServer @Agent가 수동 builder 없이 ASGI host에 mount된다."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_build_app()),
        base_url="http://testserver",
    ) as client:
        card_response = await client.get("/a2a/auto_a2a/.well-known/agent-card.json")
        run_response = await client.post(
            f"/a2a/auto_a2a{DEFAULT_RPC_URL}",
            json=_send("message/send", _user_message("hi")),
        )

    assert card_response.status_code == 200
    assert card_response.json()["name"] == "auto_a2a"
    result = run_response.json()["result"]
    assert result["status"]["state"] == "completed"
