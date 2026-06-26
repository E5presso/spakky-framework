"""Plugin initialization for the MCP external server adapter."""

from spakky.core.application.application import SpakkyApplication
from spakky.agent import IAgentRunnerFactory

from spakky.plugins.mcp.auth import IMcpHttpClientProvider, McpHttpClientProvider
from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.runtime import (
    IMcpRuntimeServerResolver,
    McpRuntimeServerResolver,
)


def initialize(app: SpakkyApplication) -> None:
    """Register MCP configuration and the external-tool runner factory."""
    app.add(McpConfig)
    app.add(McpHttpClientProvider)
    app.add(McpRuntimeServerResolver)
    app.add(McpClient)
    app.container.bind_to_type(IMcpHttpClientProvider, McpHttpClientProvider)
    app.container.bind_to_type(IMcpRuntimeServerResolver, McpRuntimeServerResolver)
    app.container.bind_to_type(IAgentRunnerFactory, McpClient)
