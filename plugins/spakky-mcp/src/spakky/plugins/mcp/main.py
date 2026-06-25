"""Plugin initialization for the MCP client adapter."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig


def initialize(app: SpakkyApplication) -> None:
    """Register MCP client configuration and the external-tool client."""
    app.add(McpConfig)
    app.add(McpClient)
