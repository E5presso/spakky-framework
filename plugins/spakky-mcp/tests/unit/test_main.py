"""Tests for MCP client plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.main import initialize


def test_initialize_registers_mcp_config_and_client() -> None:
    """initialize() registers the MCP config and the external-tool client."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(McpConfig)
    assert app.container.contains(McpClient)
    app.start()
    assert isinstance(app.container.get(McpClient), McpClient)
