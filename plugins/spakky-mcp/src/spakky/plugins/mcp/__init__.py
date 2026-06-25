"""MCP client adapter plugin joining external server tools to the agent catalog."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.mcp.client import (
    McpClient,
    connect_server,
    make_mcp_tool_callable,
)
from spakky.plugins.mcp.config import (
    McpConfig,
    McpServerConfig,
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
    McpToolInvocationError,
    McpTransportError,
)

PLUGIN_NAME = Plugin(name="spakky-mcp")
"""Plugin identifier for the MCP client adapter package."""

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
    "McpToolInvocationError",
    "McpTransport",
    "McpTransportError",
    "build_external_descriptor",
    "build_external_descriptors",
    "build_mcp_runner",
    "connect_server",
    "make_mcp_tool_callable",
    "merge_external_catalog",
    "normalize_call_result",
    "prefixed_tool_name",
]
