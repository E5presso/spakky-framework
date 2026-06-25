"""Tests for MCP plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.main import initialize
from spakky.plugins.mcp.server import McpToolServer


def test_initialize_registers_mcp_config_client_and_tool_server() -> None:
    """initialize() registers the MCP config, the client and the tool server."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(McpConfig)
    assert app.container.contains(McpClient)
    assert app.container.contains(McpToolServer)
    app.start()
    assert isinstance(app.container.get(McpClient), McpClient)
    assert isinstance(app.container.get(McpToolServer), McpToolServer)
