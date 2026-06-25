"""Unit coverage for the MCP tool server building blocks."""

import json
from collections.abc import AsyncGenerator

import pytest
from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    TextContent,
)
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentToolCatalog,
    AgentYield,
    AgentYieldKind,
    Final,
    Idempotency,
    JsonValue,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)

from spakky.plugins.mcp.config import McpConfig, McpToolServerConfig
from spakky.plugins.mcp.server import (
    McpToolServer,
    build_agent_tool_server,
    build_agent_tools,
    normalize_dispatch_result,
    serve_stdio,
    streamable_http_session_manager,
)


@Agent(spec=AgentExecutionSpec(name="unit", objective="serve tools"))
class ToolAgent:
    """Agent fixture with one native tool used across server unit tests."""

    @agent_tool(
        schema_name="echo",
        description="Return the value unchanged.",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def echo(self, value: str) -> str:
        """Return the value unchanged."""
        return value

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Satisfy the @Agent execute contract."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )


def test_build_agent_tools_maps_descriptor_name_description_and_schema() -> None:
    """Each catalog descriptor becomes a tool carrying its name and input schema."""
    tools = build_agent_tools(Agent.get(ToolAgent).tool_catalog)

    tool = next(tool for tool in tools if tool.name == "echo")
    assert tool.description == "Return the value unchanged."
    assert tool.inputSchema["properties"] == {"value": {"type": "string"}}


def test_build_agent_tools_on_empty_catalog_expect_no_tools() -> None:
    """An empty catalog yields no tool definitions."""
    assert build_agent_tools(AgentToolCatalog()) == []


def test_normalize_dispatch_result_scalar_expect_wrapped_under_result() -> None:
    """A scalar result is wrapped under the ``result`` structured key."""
    content, structured = normalize_dispatch_result("done")

    assert structured == {"result": "done"}
    assert content == [TextContent(type="text", text=json.dumps({"result": "done"}))]


def test_normalize_dispatch_result_mapping_expect_structured_as_is() -> None:
    """A mapping result is exposed as structured content without wrapping."""
    payload: dict[str, JsonValue] = {"city": "seoul", "ok": True}

    content, structured = normalize_dispatch_result(payload)

    assert structured == payload
    assert content == [TextContent(type="text", text=json.dumps(payload))]


async def test_build_agent_tool_server_dispatch_failure_surfaces_error_result() -> None:
    """A handler dispatch failure is reported to the SDK as a tool error."""
    server = build_agent_tool_server(ToolAgent(), "spakky-agent")
    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="echo", arguments={"missing": "arg"}),
    )

    result = await server.request_handlers[CallToolRequest](request)

    tool_result = result.root
    assert isinstance(tool_result, CallToolResult)
    assert tool_result.isError is True


def test_streamable_http_session_manager_wraps_server() -> None:
    """The streamable-HTTP helper returns a session manager bound to the server."""
    server = build_agent_tool_server(ToolAgent(), "spakky-agent")

    manager = streamable_http_session_manager(server)

    assert isinstance(manager, StreamableHTTPSessionManager)


async def test_serve_stdio_runs_until_streams_close(monkeypatch) -> None:
    """serve_stdio drives the server over the stdio transport streams."""
    server = build_agent_tool_server(ToolAgent(), "spakky-agent")
    run_calls: list[tuple[object, object]] = []

    class _Streams:
        async def __aenter__(self) -> tuple[object, object]:
            return ("read", "write")

        async def __aexit__(self, *_: object) -> None:
            return None

    async def _run(read: object, write: object, _options: object) -> None:
        run_calls.append((read, write))

    monkeypatch.setattr("spakky.plugins.mcp.server.stdio_server", lambda: _Streams())
    monkeypatch.setattr(server, "run", _run)

    await serve_stdio(server)

    assert run_calls == [("read", "write")]


@pytest.fixture
def tool_server() -> McpToolServer:
    """The MCP tool server Pod wired with a named tool-server identity."""
    config = McpConfig()
    config.tool_server = McpToolServerConfig(name="named-agent")
    return McpToolServer(config)


def test_tool_server_build_server_uses_configured_name(
    tool_server: McpToolServer,
) -> None:
    """The Pod builds a server advertising the configured identity."""
    server = tool_server.build_server(ToolAgent())

    assert isinstance(server, Server)
    assert server.name == "named-agent"


def test_tool_server_streamable_http_session_manager_wraps_built_server(
    tool_server: McpToolServer,
) -> None:
    """The Pod exposes a streamable-HTTP manager for the built server."""
    manager = tool_server.streamable_http_session_manager(ToolAgent())

    assert isinstance(manager, StreamableHTTPSessionManager)


async def test_tool_server_serve_stdio_delegates_to_built_server(monkeypatch) -> None:
    """The Pod's serve_stdio drives the server it builds over stdio."""
    served: list[Server] = []

    async def _serve(server: Server) -> None:
        served.append(server)

    monkeypatch.setattr("spakky.plugins.mcp.server.serve_stdio", _serve)
    config = McpConfig()
    config.tool_server = McpToolServerConfig(name="named-agent")

    await McpToolServer(config).serve_stdio(ToolAgent())

    assert served[0].name == "named-agent"
