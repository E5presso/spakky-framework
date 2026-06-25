"""Plugin initialization for the MCP client and server adapters."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.server import McpToolServer


def initialize(app: SpakkyApplication) -> None:
    """Register MCP configuration, the external-tool client and the tool server."""
    app.add(McpConfig)
    app.add(McpClient)
    app.add(McpToolServer)
