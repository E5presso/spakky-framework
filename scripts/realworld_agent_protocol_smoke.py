"""Run localhost smoke tests across Agent, MCP, AG-UI, and A2A adapters.

This is intentionally outside pytest. It opens real stdio/socket transports and
fails fast when the documented protocol paths do not execute end to end.
"""

import asyncio
import json
import socket
import sys
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import override

import grpc.aio
import httpx
import uvicorn
import websockets
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    TaskState,
)
from a2a.utils import DEFAULT_RPC_URL
from ag_ui.core import RunAgentInput as AgUiRunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI
from google.protobuf.message import Message as ProtobufMessage
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
from spakky.agent.event import ToolCallResultEvent
from spakky.agent.interfaces.model import IAgentModel
from spakky.plugins.a2a.grpc_transport.builder import build_a2a_grpc_handler
from spakky.plugins.a2a.grpc_transport.handler import A2A_GRPC_SERVICE
from spakky.plugins.a2a.rest_transport.builder import build_a2a_rest_app
from spakky.plugins.a2a.server.builder import build_a2a_app
from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import add_agui_endpoint
from spakky.plugins.agui.http_stream import add_agui_http_stream_endpoint
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver
from spakky.plugins.agui.websocket import add_agui_websocket_endpoint
from spakky.plugins.grpc.server_spec import GrpcServerSpec
from spakky.plugins.mcp import (
    MCP_CALL_TOOL_NAME,
    MCP_SEARCH_TOOLS_NAME,
    McpClient,
    McpConfig,
    McpServerConfig,
)
from starlette.types import ASGIApp

type JsonObject = dict[str, object]


class TokenModel(IAgentModel):
    """Model adapter that streams deterministic text."""

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
            token_delta="hello ",
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOKEN_DELTA,
            token_delta="world",
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class ToolModel(IAgentModel):
    """Model adapter that calls one native Agent tool."""

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
            token_delta="checking",
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name="lookup",
                arguments={"topic": "agents"},
                call_id="agui-call-1",
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


class McpToolModel(IAgentModel):
    """Model adapter that exercises Spakky MCP lazy search then lazy call."""

    @property
    @override
    def capability(self) -> ModelCapability:
        return ModelCapability()

    @override
    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="scripted")

    @override
    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        tool_names = (
            {tool.name for tool in request.tool_calling.tools}
            if request.tool_calling is not None
            else set()
        )
        if (
            MCP_SEARCH_TOOLS_NAME not in tool_names
            or MCP_CALL_TOOL_NAME not in tool_names
        ):
            msg = "MCP lazy tools were not exposed to the model request"
            raise RuntimeError(msg)
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name=MCP_SEARCH_TOOLS_NAME,
                arguments={"query": "forecast", "limit": 5},
                call_id="mcp-search-1",
            ),
        )
        yield ModelStreamEvent(
            kind=ModelStreamEventKind.TOOL_CALL_CANDIDATE,
            tool_call=ModelToolCall(
                name=MCP_CALL_TOOL_NAME,
                arguments={
                    "tool_name": "weather__forecast",
                    "arguments": {"city": "seoul"},
                },
                call_id="mcp-call-1",
            ),
        )
        yield ModelStreamEvent(kind=ModelStreamEventKind.DONE)


@Agent(spec=AgentExecutionSpec(name="smoke_mcp_agent", objective="use MCP tools"))
class McpSmokeAgent:
    """Agent with no native tools; MCP tools are supplied at runtime."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


@Agent(spec=AgentExecutionSpec(name="smoke_agui_agent", objective="serve AG-UI"))
class AgUiSmokeAgent:
    """Agent served through AG-UI transports."""

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


@Agent(spec=AgentExecutionSpec(name="smoke_a2a_agent", objective="serve A2A"))
class A2ASmokeAgent:
    """Stateless Agent served through A2A transports."""

    def __init__(self, model: IAgentModel) -> None:
        self._model = model


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _serve_asgi(app: ASGIApp) -> tuple[str, uvicorn.Server, asyncio.Task[None]]:
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        lifespan="off",
        log_level="error",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            return f"http://127.0.0.1:{port}", server, task
        await asyncio.sleep(0.05)
    server.should_exit = True
    await task
    msg = "ASGI server did not start"
    raise RuntimeError(msg)


async def _stop_asgi(server: uvicorn.Server, task: asyncio.Task[None]) -> None:
    server.should_exit = True
    await task


def _agui_payload(run_id: str) -> JsonObject:
    return {
        "threadId": "thread-1",
        "runId": run_id,
        "state": None,
        "messages": [{"id": "u1", "role": "user", "content": "look up agents"}],
        "tools": [],
        "context": [],
        "forwardedProps": {"mcp": {"servers": []}},
    }


def _sse_payloads(body: str) -> list[JsonObject]:
    payloads: list[JsonObject] = []
    for frame in body.split("\n\n"):
        if frame.startswith("data: "):
            payload = json.loads(frame.removeprefix("data: ").strip())
            if isinstance(payload, dict):
                payloads.append(payload)
    return payloads


def _event_types(payloads: Sequence[JsonObject]) -> list[str]:
    return [str(payload["type"]) for payload in payloads if "type" in payload]


async def smoke_mcp_agent() -> None:
    config = McpConfig()
    config.servers = (
        McpServerConfig(
            name="weather",
            command=sys.executable,
            args=(str(Path(__file__).with_name("smoke_mcp_stdio_server.py")),),
            call_timeout_seconds=10.0,
        ),
    )
    config.connect_timeout_seconds = 10.0
    client = McpClient(config)
    run_input = RunAgentInput(
        state_id="mcp-run-1",
        conversation_id="thread-1",
        instruction="Use the weather MCP server.",
        metadata={"mcp": {"servers": ["weather"]}},
    )
    agent = McpSmokeAgent(McpToolModel())

    async with client.open_runner(agent, run_input=run_input) as runner:
        events = [event async for event in runner.run_events(run_input)]

    results = [event for event in events if isinstance(event, ToolCallResultEvent)]
    if len(results) != 2:
        msg = f"Expected 2 MCP tool results, got {len(results)}"
        raise RuntimeError(msg)
    search_result = results[0].result
    call_result = results[1].result
    if not isinstance(search_result, dict) or not isinstance(call_result, dict):
        msg = "MCP result payloads were not JSON objects"
        raise RuntimeError(msg)
    tools = search_result.get("tools")
    if not isinstance(tools, list) or not tools or not isinstance(tools[0], dict):
        msg = f"Unexpected MCP search result: {search_result}"
        raise RuntimeError(msg)
    first_tool = tools[0]
    if first_tool.get("name") != "weather__forecast":
        msg = f"Unexpected MCP search result: {search_result}"
        raise RuntimeError(msg)
    if call_result != {"result": "sunny in seoul"}:
        msg = f"Unexpected MCP call result: {call_result}"
        raise RuntimeError(msg)
    print(
        "MCP_OK "
        "transport=stdio-process "
        "agent_tools=mcp_search_tools,mcp_call_tool "
        "result=sunny in seoul",
        flush=True,
    )


def _build_agui_app() -> FastAPI:
    app = FastAPI()
    config = AgUiConfig()
    agent = AgUiSmokeAgent(ToolModel())

    def run_driver_factory(
        core_input: RunAgentInput,
        ag_ui_input: AgUiRunAgentInput,
        accept: str | None,
    ) -> AgUiRunDriver:
        _ = ag_ui_input
        runner = AgentRunner.for_agent_instance(agent)
        return AgUiRunDriver(
            runner=runner,
            run_input=core_input,
            agent_id="smoke_agui_agent",
            projector=AgUiProjector(config),
            encoder=EventEncoder(accept=accept or ""),
        )

    add_agui_endpoint(app, run_driver_factory=run_driver_factory, config=config)
    add_agui_http_stream_endpoint(
        app,
        run_driver_factory=run_driver_factory,
        config=config,
    )
    add_agui_websocket_endpoint(
        app,
        run_driver_factory=run_driver_factory,
        config=config,
    )
    return app


async def smoke_agui() -> None:
    base_url, server, task = await _serve_asgi(_build_agui_app())
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            sse = await client.post("/agui", json=_agui_payload("agui-sse-run"))
            sse.raise_for_status()
            sse_types = _event_types(_sse_payloads(sse.text))

            stream = await client.post(
                "/agui/stream",
                json=_agui_payload("agui-http-run"),
            )
            stream.raise_for_status()
            stream_payloads = [
                json.loads(line) for line in stream.text.splitlines() if line.strip()
            ]
            stream_types = _event_types(stream_payloads)

        ws_types: list[str] = []
        async with websockets.connect(
            base_url.replace("http://", "ws://") + "/agui/ws"
        ) as websocket:
            await websocket.send(json.dumps(_agui_payload("agui-ws-run")))
            while True:
                raw = await websocket.recv()
                payload = json.loads(str(raw).removeprefix("data: ").strip())
                ws_types.append(str(payload["type"]))
                if payload["type"] == "RUN_FINISHED":
                    break
    finally:
        await _stop_asgi(server, task)

    for label, types in (
        ("sse", sse_types),
        ("http_stream", stream_types),
        ("websocket", ws_types),
    ):
        if types[0] != "RUN_STARTED" or "TOOL_CALL_RESULT" not in types:
            msg = f"AG-UI {label} did not run the Agent tool: {types}"
            raise RuntimeError(msg)
        if types[-1] != "RUN_FINISHED":
            msg = f"AG-UI {label} did not finish: {types}"
            raise RuntimeError(msg)
    print(
        "AGUI_OK transports=sse,http_stream,websocket agent_tool_result=fact:agents",
        flush=True,
    )


def _a2a_json_rpc(method: str, params: JsonObject) -> JsonObject:
    return {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}


def _a2a_rpc_message(text: str) -> JsonObject:
    return {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": "m1",
        }
    }


def _a2a_rest_message(text: str) -> JsonObject:
    return {
        "message": {
            "role": "ROLE_USER",
            "messageId": "m1",
            "parts": [{"text": text}],
        }
    }


def _rpc_sse_states(body: str) -> list[str]:
    states: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        result = json.loads(line[len("data:") :].strip())["result"]
        if "status" in result:
            states.append(str(result["status"]["state"]))
    return states


def _rest_sse_states(body: str) -> list[str]:
    states: list[str] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[len("data:") :].strip())
        task = payload.get("task")
        if isinstance(task, dict):
            status = task.get("status")
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                states.append(status["state"])
        update = payload.get("statusUpdate")
        if isinstance(update, dict):
            status = update.get("status")
            if isinstance(status, dict) and isinstance(status.get("state"), str):
                states.append(status["state"])
    return states


def _a2a_agent() -> A2ASmokeAgent:
    return A2ASmokeAgent(TokenModel())


async def smoke_a2a_jsonrpc() -> None:
    base_url, server, task = await _serve_asgi(
        build_a2a_app(
            _a2a_agent(),
            base_url="http://127.0.0.1/a2a",
            version="1.0.0",
        )
    )
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            card = await client.get("/.well-known/agent-card.json")
            card.raise_for_status()
            sent = await client.post(
                DEFAULT_RPC_URL,
                json=_a2a_json_rpc("message/send", _a2a_rpc_message("hi")),
            )
            sent.raise_for_status()
            result = sent.json()["result"]
            async with client.stream(
                "POST",
                DEFAULT_RPC_URL,
                json=_a2a_json_rpc("message/stream", _a2a_rpc_message("hi")),
            ) as response:
                response.raise_for_status()
                stream_body = (await response.aread()).decode()
    finally:
        await _stop_asgi(server, task)

    if result["status"]["state"] != "completed":
        msg = f"A2A JSON-RPC send did not complete: {result}"
        raise RuntimeError(msg)
    states = _rpc_sse_states(stream_body)
    if states[0] != "submitted" or states[-1] != "completed":
        msg = f"A2A JSON-RPC stream states were wrong: {states}"
        raise RuntimeError(msg)
    print(
        "A2A_JSONRPC_OK transport=http+jsonrpc+sse states=" + ",".join(states),
        flush=True,
    )


async def smoke_a2a_rest() -> None:
    headers = {"A2A-Version": "1.0"}
    base_url, server, task = await _serve_asgi(
        build_a2a_rest_app(
            _a2a_agent(),
            base_url="http://127.0.0.1/a2a-rest",
            version="1.0.0",
        )
    )
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            sent = await client.post(
                "/message:send",
                json=_a2a_rest_message("hi"),
                headers=headers,
            )
            sent.raise_for_status()
            task_body = sent.json()["task"]
            async with client.stream(
                "POST",
                "/message:stream",
                json=_a2a_rest_message("hi"),
                headers=headers,
            ) as response:
                response.raise_for_status()
                stream_body = (await response.aread()).decode()
    finally:
        await _stop_asgi(server, task)

    if task_body["status"]["state"] != "TASK_STATE_COMPLETED":
        msg = f"A2A REST send did not complete: {task_body}"
        raise RuntimeError(msg)
    states = _rest_sse_states(stream_body)
    if states[0] != "TASK_STATE_SUBMITTED" or states[-1] != "TASK_STATE_COMPLETED":
        msg = f"A2A REST stream states were wrong: {states}"
        raise RuntimeError(msg)
    print(
        "A2A_REST_OK transport=http+json+sse states=" + ",".join(states),
        flush=True,
    )


def _serialize(message: ProtobufMessage) -> bytes:
    return message.SerializeToString()


def _deserialize_message(message_type: type[ProtobufMessage]):
    def deserialize(data: bytes) -> ProtobufMessage:
        message = message_type()
        message.ParseFromString(data)
        return message

    return deserialize


def _grpc_method(name: str) -> str:
    return f"/{A2A_GRPC_SERVICE}/{name}"


def _grpc_message(text: str) -> Message:
    return Message(
        role=Role.ROLE_USER,
        message_id="m1",
        parts=[Part(text=text)],
    )


async def smoke_a2a_grpc() -> None:
    spec = GrpcServerSpec()
    spec.add_insecure_port("127.0.0.1:0")
    spec.add_handler(
        build_a2a_grpc_handler(
            _a2a_agent(),
            base_url="grpc://127.0.0.1/a2a",
            version="1.0.0",
        )
    )
    server = await spec.build_async()
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{spec.bound_ports[0]}")
    try:
        send = channel.unary_unary(
            _grpc_method("SendMessage"),
            request_serializer=_serialize,
            response_deserializer=_deserialize_message(SendMessageResponse),
        )
        response = await send(SendMessageRequest(message=_grpc_message("hi")))
        if not isinstance(response, SendMessageResponse):
            msg = "A2A gRPC response type mismatch"
            raise RuntimeError(msg)
        if response.task.status.state != TaskState.TASK_STATE_COMPLETED:
            msg = f"A2A gRPC send did not complete: {response.task.status.state}"
            raise RuntimeError(msg)

        stream = channel.unary_stream(
            _grpc_method("SendStreamingMessage"),
            request_serializer=_serialize,
            response_deserializer=_deserialize_message(StreamResponse),
        )
        states: list[TaskState.ValueType] = []
        async for item in stream(SendMessageRequest(message=_grpc_message("hi"))):
            if not isinstance(item, StreamResponse):
                msg = "A2A gRPC stream response type mismatch"
                raise RuntimeError(msg)
            if item.HasField("task"):
                states.append(item.task.status.state)
            if item.HasField("status_update"):
                states.append(item.status_update.status.state)
    finally:
        await channel.close()
        await server.stop(grace=0)

    if states[0] != TaskState.TASK_STATE_SUBMITTED:
        msg = f"A2A gRPC stream did not submit first: {states}"
        raise RuntimeError(msg)
    if states[-1] != TaskState.TASK_STATE_COMPLETED:
        msg = f"A2A gRPC stream did not complete: {states}"
        raise RuntimeError(msg)
    print(
        "A2A_GRPC_OK transport=grpc states=" + ",".join(str(state) for state in states),
        flush=True,
    )


async def main() -> None:
    await smoke_mcp_agent()
    await smoke_agui()
    await smoke_a2a_jsonrpc()
    await smoke_a2a_rest()
    await smoke_a2a_grpc()
    print("REALWORLD_AGENT_PROTOCOL_SMOKE_OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
