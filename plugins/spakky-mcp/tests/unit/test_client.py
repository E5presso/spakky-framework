"""Unit tests for MCP connection lifecycle, discovery, and the tool callable."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import override

import pytest
from mcp import StdioServerParameters
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from spakky.agent import AgentRunnerFactory, IAgentModel, IAgentModelResolver
from spakky.agent import RunAgentInput
from spakky.plugins.mcp import client as client_module
from spakky.plugins.mcp.client import (
    McpClient,
    connect_server,
    make_mcp_tool_callable,
)
from spakky.plugins.mcp.descriptor import MCP_CALL_TOOL_NAME, MCP_SEARCH_TOOLS_NAME
from spakky.plugins.mcp.auth import McpHttpClientProvider
from spakky.plugins.mcp.config import McpConfig, McpServerConfig, McpTransport
from spakky.plugins.mcp.config import McpServerAuthConfig
from spakky.plugins.mcp.error import (
    McpToolDiscoveryError,
    McpToolInvocationError,
    McpTransportError,
)


class _FakeSession:
    """ClientSession double used to exercise discovery and dispatch wiring."""

    def __init__(
        self,
        tools: list[Tool] | None = None,
        list_error: Exception | None = None,
        call_error: Exception | None = None,
    ) -> None:
        self._tools = tools or []
        self._list_error = list_error
        self._call_error = call_error
        self.initialized = False
        self.last_read_timeout: timedelta | None = None

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def initialize(self) -> None:
        self.initialized = True

    async def list_tools(self) -> ListToolsResult:
        if self._list_error is not None:
            raise self._list_error
        return ListToolsResult(tools=self._tools)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        read_timeout_seconds: timedelta,
    ) -> CallToolResult:
        self.last_read_timeout = read_timeout_seconds
        if self._call_error is not None:
            raise self._call_error
        return CallToolResult(
            content=[TextContent(type="text", text=name)],
            structuredContent={"args": arguments},
        )


class _SelectedModelResolver(IAgentModelResolver):
    """Model resolver double proving MCP wraps the native runner factory."""

    def __init__(self, model: IAgentModel) -> None:
        self.model = model
        self.last_input: RunAgentInput | None = None

    @override
    def resolve_model(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None = None,
    ) -> IAgentModel | None:
        _ = agent_instance
        self.last_input = run_input
        return self.model


def _echo_tool() -> Tool:
    return Tool(
        name="echo",
        description="Echo",
        inputSchema={"type": "object", "properties": {"city": {"type": "string"}}},
    )


def _patch_session_and_streams(
    monkeypatch: pytest.MonkeyPatch,
    session: _FakeSession,
) -> None:
    @asynccontextmanager
    async def _streams(
        _server: McpServerConfig,
        _http_client: object | None = None,
    ) -> AsyncGenerator[tuple[object, object], None]:
        yield object(), object()

    monkeypatch.setattr(client_module, "_transport_streams", _streams)
    monkeypatch.setattr(
        client_module,
        "ClientSession",
        lambda _read, _write, read_timeout_seconds=None: session,
    )


async def test_make_callable_returns_normalized_structured_result() -> None:
    """The bound callable returns the normalized structured tool result."""
    session = _FakeSession()
    invoke = make_mcp_tool_callable(session, "echo", 60.0)  # type: ignore[arg-type] - fake mirrors call_tool

    result = await invoke(city="seoul")

    assert result == {"args": {"city": "seoul"}}


async def test_make_callable_forwards_configured_call_timeout() -> None:
    """The callable bounds each call with the configured per-server timeout."""
    session = _FakeSession()
    invoke = make_mcp_tool_callable(session, "echo", 12.5)  # type: ignore[arg-type] - fake mirrors call_tool

    await invoke(city="seoul")

    assert session.last_read_timeout == timedelta(seconds=12.5)


async def test_make_callable_wraps_transport_failure() -> None:
    """A raw transport failure during a call surfaces as an invocation error."""
    session = _FakeSession(call_error=RuntimeError("socket closed"))
    invoke = make_mcp_tool_callable(session, "echo", 60.0)  # type: ignore[arg-type] - fake mirrors call_tool

    with pytest.raises(McpToolInvocationError):
        await invoke(city="seoul")


async def test_make_callable_preserves_typed_invocation_error() -> None:
    """A typed invocation error from result mapping is not re-wrapped."""
    session = _FakeSession(call_error=McpToolInvocationError())
    invoke = make_mcp_tool_callable(session, "echo", 60.0)  # type: ignore[arg-type] - fake mirrors call_tool

    with pytest.raises(McpToolInvocationError):
        await invoke(city="seoul")


async def test_connect_server_discovers_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connecting a server discovers its tools as prefixed descriptors."""
    session = _FakeSession(tools=[_echo_tool()])
    _patch_session_and_streams(monkeypatch, session)
    server = McpServerConfig(name="weather", command="weather-server")

    async with connect_server(server, 30.0) as (_session, descriptors):
        assert session.initialized is True
        assert [descriptor.schema.name for descriptor in descriptors] == [
            "weather__echo"
        ]


async def test_connect_server_wraps_discovery_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A list_tools failure surfaces as a typed discovery error."""
    session = _FakeSession(list_error=RuntimeError("no tools endpoint"))
    _patch_session_and_streams(monkeypatch, session)
    server = McpServerConfig(name="weather", command="weather-server")

    with pytest.raises(McpToolDiscoveryError):
        async with connect_server(server, 30.0) as _discovered:
            pass


async def test_connect_server_wraps_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport failure on connect surfaces as a typed transport error."""

    @asynccontextmanager
    async def _failing_streams(
        _server: McpServerConfig,
        _http_client: object | None = None,
    ) -> AsyncGenerator[tuple[object, object], None]:
        _ = _http_client
        raise RuntimeError("connection refused")
        yield object(), object()  # pragma: no cover - unreachable after raise

    monkeypatch.setattr(client_module, "_transport_streams", _failing_streams)
    server = McpServerConfig(name="weather", command="weather-server")

    with pytest.raises(McpTransportError):
        async with connect_server(server, 30.0) as _discovered:
            pass


async def test_streamable_http_transport_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A streamable_http server dials through the streamable http transport."""
    used: dict[str, str] = {}

    @asynccontextmanager
    async def _fake_http(
        url: str,
    ) -> AsyncGenerator[tuple[object, object, object], None]:
        used["url"] = url
        yield object(), object(), object()

    session = _FakeSession(tools=[_echo_tool()])
    monkeypatch.setattr(client_module, "streamable_http_client", _fake_http)
    monkeypatch.setattr(
        client_module,
        "ClientSession",
        lambda _read, _write, read_timeout_seconds=None: session,
    )
    server = McpServerConfig(
        name="weather",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://example.test/mcp",
    )

    async with connect_server(server, 30.0) as (_session, descriptors):
        assert used["url"] == "https://example.test/mcp"
        assert len(descriptors) == 1


async def test_streamable_http_transport_passes_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authenticated remote MCP servers receive configured HTTP headers."""
    monkeypatch.setenv("WEATHER_MCP_TOKEN", "token-123")
    captured: dict[str, str] = {}

    @asynccontextmanager
    async def _fake_http(
        url: str,
        *,
        http_client: object | None = None,
        terminate_on_close: bool = True,
    ) -> AsyncGenerator[tuple[object, object, object], None]:
        captured["url"] = url
        captured["authorization"] = http_client.headers["authorization"]  # type: ignore[attr-defined] - fake inspects SDK client
        captured["api_key"] = http_client.headers["x-api-key"]  # type: ignore[attr-defined] - fake inspects SDK client
        yield object(), object(), object()

    session = _FakeSession(tools=[_echo_tool()])
    monkeypatch.setattr(client_module, "streamable_http_client", _fake_http)
    monkeypatch.setattr(
        client_module,
        "ClientSession",
        lambda _read, _write, read_timeout_seconds=None: session,
    )
    server = McpServerConfig(
        name="weather",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://example.test/mcp",
        auth=McpServerAuthConfig(
            headers={"X-Api-Key": "static-key"},
            bearer_token_env="WEATHER_MCP_TOKEN",
        ),
    )

    async with McpHttpClientProvider().open_client(server) as http_client:
        async with connect_server(server, 30.0, http_client) as (
            _session,
            descriptors,
        ):
            assert len(descriptors) == 1

    assert captured == {
        "url": "https://example.test/mcp",
        "authorization": "Bearer token-123",
        "api_key": "static-key",
    }


async def test_stdio_transport_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stdio server dials through the stdio transport with its command."""
    captured: list[StdioServerParameters] = []

    @asynccontextmanager
    async def _fake_stdio(
        parameters: StdioServerParameters,
    ) -> AsyncGenerator[tuple[object, object], None]:
        captured.append(parameters)
        yield object(), object()

    session = _FakeSession(tools=[_echo_tool()])
    monkeypatch.setattr(client_module, "stdio_client", _fake_stdio)
    monkeypatch.setattr(
        client_module,
        "ClientSession",
        lambda _read, _write, read_timeout_seconds=None: session,
    )
    server = McpServerConfig(
        name="weather",
        command="weather-server",
        args=("--verbose",),
        env={"TOKEN": "x"},
    )

    async with connect_server(server, 30.0) as (_session, descriptors):
        assert captured[0].command == "weather-server"
        assert captured[0].args == ["--verbose"]
        assert len(descriptors) == 1


async def test_open_runner_with_no_servers_yields_native_only_runner() -> None:
    """With no servers declared, the runner carries only native catalog tools."""
    from tests.unit.test_catalog_merge import WeatherAgent, _StubModel

    client = McpClient(McpConfig())
    agent = WeatherAgent(_StubModel())

    async with client.open_runner(agent) as runner:
        names = {
            descriptor.schema.name
            for descriptor in runner.agent.tool_catalog.descriptors
        }
        assert names == {"local.now"}


async def test_open_runner_preserves_native_model_resolver() -> None:
    """MCP runner augmentation does not bypass request-scoped model resolution."""
    from tests.unit.test_catalog_merge import WeatherAgent, _StubModel

    selected = _StubModel()
    resolver = _SelectedModelResolver(selected)
    run_input = RunAgentInput(state_id="run-1", instruction="answer")
    client = McpClient(
        McpConfig(),
        runner_factory=AgentRunnerFactory(model_resolver=resolver),
    )

    async with client.open_runner(
        WeatherAgent(_StubModel()), run_input=run_input
    ) as runner:
        assert runner.model is selected

    assert resolver.last_input is run_input


async def test_open_runner_merges_named_server_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run metadata selects configured servers behind lazy MCP catalog tools."""
    from tests.unit.test_catalog_merge import WeatherAgent, _StubModel

    session = _FakeSession(tools=[_echo_tool()])
    _patch_session_and_streams(monkeypatch, session)
    config = McpConfig()
    config.servers = (McpServerConfig(name="weather", command="weather-server"),)
    client = McpClient(config)
    agent = WeatherAgent(_StubModel())

    async with client.open_runner(
        agent,
        run_input=RunAgentInput(
            state_id="run-1",
            instruction="answer",
            metadata={"mcp": {"servers": ["weather"]}},
        ),
    ) as runner:
        names = {
            descriptor.schema.name
            for descriptor in runner.agent.tool_catalog.descriptors
        }
        assert names == {"local.now", MCP_SEARCH_TOOLS_NAME, MCP_CALL_TOOL_NAME}


async def test_open_runner_uses_run_input_mcp_server_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run metadata selects user/service MCP servers for one Agent run."""
    from tests.unit.test_catalog_merge import WeatherAgent, _StubModel

    session = _FakeSession(tools=[_echo_tool()])
    _patch_session_and_streams(monkeypatch, session)
    config = McpConfig()
    config.servers = (
        McpServerConfig(name="weather", command="weather-server"),
        McpServerConfig(name="unused", command="unused-server"),
    )
    client = McpClient(config)
    agent = WeatherAgent(_StubModel())

    async with client.open_runner(
        agent,
        run_input=RunAgentInput(
            state_id="run-2",
            instruction="answer",
            metadata={"mcp": {"servers": ["weather"]}},
        ),
    ) as runner:
        names = {
            descriptor.schema.name
            for descriptor in runner.agent.tool_catalog.descriptors
        }
        assert names == {"local.now", MCP_SEARCH_TOOLS_NAME, MCP_CALL_TOOL_NAME}


async def test_open_runner_accepts_inline_runtime_mcp_server_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run metadata can carry inline MCP server declarations from user settings."""
    from tests.unit.test_catalog_merge import WeatherAgent, _StubModel

    session = _FakeSession(tools=[_echo_tool()])
    _patch_session_and_streams(monkeypatch, session)
    client = McpClient(McpConfig())
    agent = WeatherAgent(_StubModel())

    async with client.open_runner(
        agent,
        run_input=RunAgentInput(
            state_id="run-3",
            instruction="answer",
            metadata={
                "mcp": {
                    "servers": [
                        {"name": "github", "command": "github-mcp-server"},
                    ]
                }
            },
        ),
    ) as runner:
        names = {
            descriptor.schema.name
            for descriptor in runner.agent.tool_catalog.descriptors
        }
        assert names == {"local.now", MCP_SEARCH_TOOLS_NAME, MCP_CALL_TOOL_NAME}
