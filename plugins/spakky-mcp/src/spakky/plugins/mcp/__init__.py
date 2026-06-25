"""MCP adapter plugin bridging external server tools and the agent catalog.

Joins external MCP server tools into the agent tool catalog (client side,
issue #416) and exposes an agent's own tools as an MCP server (server side,
issue #417).
"""

from spakky.core.application.plugin import Plugin

from spakky.plugins.mcp.client import (
    McpClient,
    connect_server,
    make_mcp_tool_callable,
)
from spakky.plugins.mcp.config import (
    McpConfig,
    McpServerConfig,
    McpToolServerConfig,
    McpTransport,
)
from spakky.plugins.mcp.descriptor import (
    ExternalMcpTool,
    ExternalMcpToolDescriptor,
    build_external_descriptor,
    build_external_descriptors,
    build_mcp_runner,
    merge_external_catalog,
    normalize_call_result,
    prefixed_tool_name,
)
from spakky.plugins.mcp.error import (
    AbstractMcpError,
    McpCatalogMergeError,
    McpResponseError,
    McpServerConfigurationError,
    McpToolDiscoveryError,
    McpToolExposureError,
    McpToolInvocationError,
    McpTransportError,
)
from spakky.plugins.mcp.server import (
    McpToolServer,
    build_agent_tool_server,
    build_agent_tools,
    normalize_dispatch_result,
    serve_stdio,
    streamable_http_session_manager,
)

PLUGIN_NAME = Plugin(name="spakky-mcp")
"""Plugin identifier for the MCP adapter package."""

__all__ = [
    "PLUGIN_NAME",
    "AbstractMcpError",
    "ExternalMcpTool",
    "ExternalMcpToolDescriptor",
    "McpCatalogMergeError",
    "McpClient",
    "McpConfig",
    "McpResponseError",
    "McpServerConfig",
    "McpServerConfigurationError",
    "McpToolDiscoveryError",
    "McpToolExposureError",
    "McpToolInvocationError",
    "McpToolServer",
    "McpToolServerConfig",
    "McpTransport",
    "McpTransportError",
    "build_agent_tool_server",
    "build_agent_tools",
    "build_external_descriptor",
    "build_external_descriptors",
    "build_mcp_runner",
    "connect_server",
    "make_mcp_tool_callable",
    "merge_external_catalog",
    "normalize_call_result",
    "normalize_dispatch_result",
    "prefixed_tool_name",
    "serve_stdio",
    "streamable_http_session_manager",
]
