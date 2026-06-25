"""End-to-end acceptance: external MCP clients discover and call agent tools.

Drives the agent tool server over the SDK's in-memory client session: an
external ``ClientSession`` lists the agent's tools and invokes one, exercising
the same ``AgentToolDispatcher`` path the framework runner dispatches native
tool calls through (issue #417 SC-1).
"""

from collections.abc import AsyncGenerator

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentYield,
    AgentYieldKind,
    Final,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)

from spakky.plugins.mcp.config import McpConfig, McpToolServerConfig
from spakky.plugins.mcp.server import McpToolServer, build_agent_tool_server


@Agent(spec=AgentExecutionSpec(name="catalog", objective="serve tools"))
class CatalogAgent:
    """Agent fixture exposing tools whose results cover both result shapes."""

    @agent_tool(
        schema_name="forecast",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def forecast(self, city: str) -> str:
        """Return a canned forecast for a city."""
        return f"sunny in {city}"

    @agent_tool(
        schema_name="lookup",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def lookup(self, key: str) -> dict[str, str | bool]:
        """Return a mapping result keyed by the requested key."""
        return {"key": key, "found": True}

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Satisfy the @Agent execute contract."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )


async def test_external_client_discovers_agent_tools_with_schema() -> None:
    """An external MCP client lists the agent's tools with their input schema."""
    server = build_agent_tool_server(CatalogAgent(), "spakky-agent")
    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()
        listed = await session.list_tools()

    by_name = {tool.name: tool for tool in listed.tools}
    assert set(by_name) == {"forecast", "lookup"}
    assert by_name["forecast"].inputSchema["properties"] == {"city": {"type": "string"}}


async def test_external_client_calls_scalar_tool_expect_wrapped_result() -> None:
    """A scalar tool result is exposed under the ``result`` structured key."""
    server = build_agent_tool_server(CatalogAgent(), "spakky-agent")
    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()
        result = await session.call_tool("forecast", arguments={"city": "seoul"})

    assert result.isError is False
    assert result.structuredContent == {"result": "sunny in seoul"}


async def test_external_client_calls_mapping_tool_expect_structured_result() -> None:
    """A mapping tool result is exposed as structured content as is."""
    server = build_agent_tool_server(CatalogAgent(), "spakky-agent")
    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()
        result = await session.call_tool("lookup", arguments={"key": "alpha"})

    assert result.isError is False
    assert result.structuredContent == {"key": "alpha", "found": True}


async def test_external_client_calls_unknown_tool_expect_error_result() -> None:
    """Dispatching a tool the catalog does not contain reports a tool error."""
    server = build_agent_tool_server(CatalogAgent(), "spakky-agent")
    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()
        result = await session.call_tool("absent", arguments={})

    assert result.isError is True


@pytest.fixture
def tool_server() -> McpToolServer:
    """The MCP tool server Pod wired with default configuration."""
    config = McpConfig()
    config.tool_server = McpToolServerConfig(name="spakky-agent")
    return McpToolServer(config)


async def test_tool_server_pod_builds_server_exposing_agent_tools(
    tool_server: McpToolServer,
) -> None:
    """The Pod builds a server an external client discovers tools through."""
    server = tool_server.build_server(CatalogAgent())
    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()
        result = await session.call_tool("forecast", arguments={"city": "busan"})

    assert result.structuredContent == {"result": "sunny in busan"}
