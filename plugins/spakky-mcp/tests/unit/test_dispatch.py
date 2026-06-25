"""Unit tests proving external MCP tools dispatch via the owner-less path."""

from datetime import timedelta

from mcp.types import CallToolResult, TextContent, Tool
from spakky.agent import AgentToolCatalog, AgentToolDispatcher
from spakky.agent.interfaces.model import ModelToolCall

from spakky.plugins.mcp.client import make_mcp_tool_callable
from spakky.plugins.mcp.descriptor import build_external_descriptor


class _RecordingSession:
    """Session double recording the raw tool name and arguments it receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        read_timeout_seconds: timedelta,
    ) -> CallToolResult:
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[TextContent(type="text", text="ok")],
            structuredContent={"echo": arguments},
        )


def _catalog(session: _RecordingSession) -> AgentToolCatalog:
    tool = Tool(
        name="echo",
        description="Echo arguments",
        inputSchema={"type": "object", "properties": {"city": {"type": "string"}}},
    )
    descriptor = build_external_descriptor(
        "weather",
        tool,
        make_mcp_tool_callable(session, "echo", 60.0),  # type: ignore[arg-type] - test double mirrors ClientSession.call_tool
    )
    return AgentToolCatalog(descriptors=(descriptor,))


async def test_dispatch_invokes_external_tool_without_binding_target() -> None:
    """The dispatcher forwards model arguments to the MCP tool, target unused."""
    session = _RecordingSession()
    dispatcher = AgentToolDispatcher(target=object(), catalog=_catalog(session))

    result = await dispatcher.dispatch(
        ModelToolCall(
            name="weather__echo",
            arguments={"city": "seoul"},
            call_id="call-1",
        )
    )

    assert session.calls == [("echo", {"city": "seoul"})]
    assert result == {"echo": {"city": "seoul"}}
