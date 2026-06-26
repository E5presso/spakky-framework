"""Tests for MCP plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.agent import IAgentRunnerFactory

from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.main import initialize


def test_initialize_registers_mcp_config_and_runner_factory() -> None:
    """initialize() registers MCP Pods and binds the runner factory port."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(McpConfig)
    assert app.container.contains(McpClient)
    assert app.container.contains(IAgentRunnerFactory)
    app.start()
    assert isinstance(app.container.get(McpClient), McpClient)
    assert isinstance(app.container.get(IAgentRunnerFactory), McpClient)
