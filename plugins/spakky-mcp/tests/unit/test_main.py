"""Tests for MCP plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.agent import IAgentRunnerFactory

from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import McpConfig
from spakky.plugins.mcp.main import initialize
from spakky.plugins.mcp.post_processors.register_tool_server_agents import (
    RegisterMcpToolServerAgentsPostProcessor,
)
from spakky.plugins.mcp.server import McpToolServer
from spakky.plugins.mcp.server_registry import McpToolServerRegistry


def test_initialize_registers_mcp_config_runner_factory_and_tool_server() -> None:
    """initialize() registers MCP Pods and binds the runner factory port."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(McpConfig)
    assert app.container.contains(McpClient)
    assert app.container.contains(IAgentRunnerFactory)
    assert app.container.contains(McpToolServerRegistry)
    assert app.container.contains(McpToolServer)
    assert app.container.contains(RegisterMcpToolServerAgentsPostProcessor)
    app.start()
    assert isinstance(app.container.get(McpClient), McpClient)
    assert isinstance(app.container.get(IAgentRunnerFactory), McpClient)
    assert isinstance(app.container.get(McpToolServerRegistry), McpToolServerRegistry)
    assert isinstance(app.container.get(McpToolServer), McpToolServer)
