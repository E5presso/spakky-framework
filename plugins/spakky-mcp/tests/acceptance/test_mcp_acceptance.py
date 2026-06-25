"""End-to-end acceptance: external MCP tools dispatch through the agent path.

Drives a real in-process MCP server (FastMCP) over the SDK's in-memory client
session, discovers its tools, normalizes them into the agent tool catalog, and
dispatches a model tool call through the real ``AgentToolDispatcher`` — the same
path native ``@agent_tool`` methods take (issue #416 SC-1).
"""

from collections.abc import AsyncGenerator

import pytest
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from spakky.agent import (
    Agent,
    AgentExecutionSpec,
    AgentToolCatalog,
    AgentToolDispatcher,
    AgentYield,
    AgentYieldKind,
    Final,
    Idempotency,
    ToolApprovalRequirement,
    ToolEffects,
    agent_tool,
)
from spakky.agent.interfaces.model import ModelToolCall

from spakky.plugins.mcp.client import make_mcp_tool_callable
from spakky.plugins.mcp.descriptor import (
    build_external_descriptors,
    merge_external_catalog,
)


@Agent(spec=AgentExecutionSpec(name="weatherer", objective="report weather"))
class WeatherAgent:
    """Agent fixture exposing one native tool alongside external MCP tools."""

    @agent_tool(
        schema_name="local.greeting",
        effects=ToolEffects.read_only(),
        idempotency=Idempotency.IDEMPOTENT,
        approval=ToolApprovalRequirement.NOT_REQUIRED,
    )
    def greeting(self) -> str:
        """Return a fixed local greeting."""
        return "hello"

    async def execute(
        self,
        command: str,
    ) -> AsyncGenerator[AgentYield[Final[str]], None]:
        """Satisfy the @Agent execute contract."""
        yield AgentYield(
            kind=AgentYieldKind.FINAL,
            payload=Final(output=command, metadata={}),
        )


@pytest.fixture
def weather_server() -> FastMCP:
    """In-process MCP server exposing one external tool."""
    server = FastMCP("acceptance")

    @server.tool()
    def forecast(city: str) -> str:
        """Return a canned forecast for a city."""
        return f"sunny in {city}"

    @server.tool()
    def join(args: list[str]) -> str:
        """Expose a tool whose input field is literally named ``args``."""
        return ",".join(args)

    return server


async def _discover(
    session: ClientSession,
    server_name: str,
) -> AgentToolCatalog:
    listed = await session.list_tools()
    descriptors = build_external_descriptors(
        server_name,
        listed.tools,
        lambda raw_tool_name: make_mcp_tool_callable(session, raw_tool_name, 60.0),
    )
    return AgentToolCatalog(descriptors=descriptors)


async def test_external_mcp_tool_dispatches_through_agent_dispatcher(
    weather_server: FastMCP,
) -> None:
    """A discovered external tool executes via the real AgentToolDispatcher."""
    async with create_connected_server_and_client_session(weather_server) as session:
        await session.initialize()
        catalog = await _discover(session, "weather")
        dispatcher = AgentToolDispatcher(target=object(), catalog=catalog)

        result = await dispatcher.dispatch(
            ModelToolCall(
                name="weather__forecast",
                arguments={"city": "seoul"},
                call_id="call-1",
            )
        )

    assert result == {"result": "sunny in seoul"}


async def test_external_tool_merges_with_native_catalog_and_both_dispatch(
    weather_server: FastMCP,
) -> None:
    """External and native tools coexist in one catalog and both dispatch."""
    async with create_connected_server_and_client_session(weather_server) as session:
        await session.initialize()
        external = await _discover(session, "weather")
        native = Agent.get(WeatherAgent).tool_catalog
        catalog = merge_external_catalog(native, external.descriptors)
        agent = WeatherAgent()
        dispatcher = AgentToolDispatcher(target=agent, catalog=catalog)

        external_result = await dispatcher.dispatch(
            ModelToolCall(
                name="weather__forecast",
                arguments={"city": "busan"},
                call_id="call-2",
            )
        )
        native_result = await dispatcher.dispatch(
            ModelToolCall(name="local.greeting", arguments={}, call_id="call-3")
        )

    assert external_result == {"result": "sunny in busan"}
    assert native_result == "hello"


async def test_external_tool_with_reserved_args_field_dispatches(
    weather_server: FastMCP,
) -> None:
    """A tool whose input field is named ``args`` executes with the field intact."""
    async with create_connected_server_and_client_session(weather_server) as session:
        await session.initialize()
        catalog = await _discover(session, "weather")
        dispatcher = AgentToolDispatcher(target=object(), catalog=catalog)

        result = await dispatcher.dispatch(
            ModelToolCall(
                name="weather__join",
                arguments={"args": ["a", "b", "c"]},
                call_id="call-4",
            )
        )

    assert result == {"result": "a,b,c"}
