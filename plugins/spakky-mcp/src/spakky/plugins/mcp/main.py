"""Plugin initialization for the MCP client and server adapters."""

from spakky.core.application.application import SpakkyApplication
from spakky.agent import IAgentRunnerFactory

from spakky.plugins.mcp.auth import IMcpHttpClientProvider, McpHttpClientProvider
from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.post_processors.register_tool_server_agents import (
    RegisterMcpToolServerAgentsPostProcessor,
)
from spakky.plugins.mcp.runtime import (
    IMcpRuntimeServerResolver,
    McpRuntimeServerResolver,
)
from spakky.plugins.mcp.server import McpToolServer
from spakky.plugins.mcp.server_registry import McpToolServerRegistry


def initialize(app: SpakkyApplication) -> None:
    """Register MCP configuration, the external-tool client and the tool server."""
    app.add(McpConfig)
    app.add(McpHttpClientProvider)
    app.add(McpRuntimeServerResolver)
    app.add(McpClient)
    app.add(McpToolServerRegistry)
    app.add(McpToolServer)
    app.add(RegisterMcpToolServerAgentsPostProcessor)
    app.container.bind_to_type(IMcpHttpClientProvider, McpHttpClientProvider)
    app.container.bind_to_type(IMcpRuntimeServerResolver, McpRuntimeServerResolver)
    app.container.bind_to_type(IAgentRunnerFactory, McpClient)
