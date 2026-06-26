"""Expose native ``@agent_tool`` tools as an MCP server (issue #417).

This is the server-side counterpart of the MCP client adapter (issue #416).
ADR-0013 §2 keeps ``core/spakky-agent`` protocol-neutral and pushes the MCP
library dependency into this adapter plugin, so the conversion of an agent's
``AgentToolCatalog`` into MCP tool definitions and the dispatch of inbound MCP
``call_tool`` requests live here rather than in the core.

An external MCP client discovers an agent's tools through the standard
``list_tools`` request — each catalog descriptor becomes an ``mcp.types.Tool``
carrying the descriptor's model-facing name, description and JSON Schema. A
``call_tool`` request runs through the same ``AgentToolDispatcher`` the
framework runner dispatches native tool calls through, so the tool a remote
client invokes behaves identically to a local model-issued tool call.
"""

import json
from collections.abc import Mapping
from typing import cast

from mcp.server.lowlevel.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import ContentBlock, TextContent, Tool
from spakky.agent import (
    Agent,
    AgentToolCatalog,
    AgentToolDispatcher,
    JsonObject,
    JsonValue,
)
from spakky.agent.interfaces.model import ModelToolCall
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.error import McpToolExposureError
from spakky.plugins.mcp.server_registry import McpToolServerEntry, McpToolServerRegistry


def build_agent_tools(catalog: AgentToolCatalog) -> list[Tool]:
    """Convert every catalog descriptor into an MCP tool definition.

    The model-facing schema name is the MCP tool name so an inbound
    ``call_tool`` resolves to the same descriptor the dispatcher keys on, and
    the descriptor's input schema is forwarded verbatim as the tool's
    ``inputSchema`` so the SDK validates arguments against the agent's contract.
    """
    return [
        Tool(
            name=descriptor.schema.name,
            description=descriptor.description,
            inputSchema=dict(descriptor.schema.input_schema),
        )
        for descriptor in catalog.descriptors
    ]


def normalize_dispatch_result(
    result: JsonValue,
) -> tuple[list[ContentBlock], JsonObject]:
    """Map a dispatched tool result into MCP content and structured content.

    MCP carries a tool result as human-readable ``content`` plus optional
    machine-readable ``structuredContent``. A mapping result is structured as
    is; any other value is wrapped under a ``result`` key so the structured
    payload is always a JSON object, mirroring the ``{"result": ...}`` shape the
    client adapter reads back (``normalize_call_result``).
    """
    structured: JsonObject = (
        dict(result) if isinstance(result, Mapping) else {"result": result}
    )
    text = json.dumps(structured)
    return [TextContent(type="text", text=text)], structured


def build_agent_tool_server(agent_instance: object, server_name: str) -> Server:
    """Build an MCP server exposing one agent instance's tool catalog.

    The catalog is read once from the agent Pod metadata; the dispatcher binds
    to the live ``agent_instance`` so a ``call_tool`` request executes the bound
    method. A failed dispatch surfaces as a typed error rather than a silent
    empty result so the SDK reports it as a tool error to the remote client.
    """
    dispatcher = AgentToolDispatcher(
        target=agent_instance,
        catalog=Agent.get(type(agent_instance)).tool_catalog,
    )
    server: Server[object, object] = Server(server_name)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return build_agent_tools(dispatcher.catalog)

    @server.call_tool()
    async def _call_tool(
        name: str,
        arguments: JsonObject,
    ) -> tuple[list[ContentBlock], JsonObject]:
        try:
            result = await dispatcher.dispatch(
                ModelToolCall(name=name, arguments=arguments)
            )
        except Exception as e:
            raise McpToolExposureError from e
        # The dispatcher returns ``object``; an agent tool result is JSON-serializable
        # by contract (the runner serializes it back to the model), so it is a JsonValue.
        return normalize_dispatch_result(cast(JsonValue, result))

    return server


async def serve_stdio(server: Server) -> None:
    """Serve the MCP server over the stdio transport until the client closes it."""
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def streamable_http_session_manager(server: Server) -> StreamableHTTPSessionManager:
    """Build the streamable-HTTP session manager wrapping the MCP server.

    The manager owns one task group for the lifetime of its ``run`` context and
    cannot be reused once that context exits; the caller drives it from the host
    application's lifespan and routes inbound requests to ``handle_request``.
    """
    return StreamableHTTPSessionManager(app=server)


@Pod()
class McpToolServer:
    """Application entry point exposing an agent's tools over an MCP transport."""

    def __init__(
        self,
        config: McpConfig,
        registry: McpToolServerRegistry | None = None,
    ) -> None:
        self.config = config
        self.registry = registry

    def build_server(self, agent_instance: object) -> Server:
        """Build an MCP server advertising the configured identity for one agent."""
        return build_agent_tool_server(agent_instance, self.config.tool_server.name)

    def build_server_for(self, agent_name: str) -> Server:
        """Build an MCP server for a registered @McpToolServerAgent name."""
        entry = self._entry(agent_name)
        return build_agent_tool_server(entry.instance, self._server_name(entry))

    async def serve_stdio(self, agent_instance: object) -> None:
        """Serve the agent's tools over stdio until the connected client closes."""
        await serve_stdio(self.build_server(agent_instance))

    async def serve_stdio_for(self, agent_name: str) -> None:
        """Serve a registered agent's tools over stdio."""
        await serve_stdio(self.build_server_for(agent_name))

    def streamable_http_session_manager(
        self,
        agent_instance: object,
    ) -> StreamableHTTPSessionManager:
        """Build the streamable-HTTP session manager exposing the agent's tools."""
        return streamable_http_session_manager(self.build_server(agent_instance))

    def streamable_http_session_manager_for(
        self,
        agent_name: str,
    ) -> StreamableHTTPSessionManager:
        """Build a streamable-HTTP manager for a registered agent."""
        return streamable_http_session_manager(self.build_server_for(agent_name))

    def _entry(self, agent_name: str) -> McpToolServerEntry:
        if self.registry is None:
            from spakky.plugins.mcp.error import McpToolServerNotRegisteredError

            raise McpToolServerNotRegisteredError(agent_name)
        return self.registry.get(agent_name)

    def _server_name(self, entry: McpToolServerEntry) -> str:
        return entry.metadata.server_name or self.config.tool_server.name
