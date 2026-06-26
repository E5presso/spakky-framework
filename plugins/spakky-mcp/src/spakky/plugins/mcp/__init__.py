"""MCP adapter plugin joining external server tools to Spakky Agents."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.mcp.auth import (
    IMcpHttpClientProvider,
    McpHttpClientProvider,
    resolve_http_auth_headers,
)
from spakky.plugins.mcp.client import McpClient
from spakky.plugins.mcp.config import (
    McpOAuthClientAuthMethod,
    McpOAuthClientCredentialsConfig,
    McpConfig,
    McpServerAuthConfig,
    McpServerConfig,
    McpTransport,
)
from spakky.plugins.mcp.descriptor import (
    DEFAULT_MCP_SEARCH_LIMIT,
    LazyMcpToolset,
    MCP_CALL_TOOL_NAME,
    MCP_SEARCH_TOOLS_NAME,
    build_lazy_mcp_descriptors,
    build_mcp_runner,
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
from spakky.plugins.mcp.runtime import (
    IMcpRuntimeServerResolver,
    MCP_METADATA_KEY,
    MCP_SERVERS_METADATA_KEY,
    McpRuntimeServerResolver,
)

PLUGIN_NAME = Plugin(name="spakky-mcp")
"""Plugin identifier for the MCP adapter package."""

MCPClient = McpClient
"""Uppercase-acronym alias for :class:`McpClient`."""

MCPConfig = McpConfig
"""Uppercase-acronym alias for :class:`McpConfig`."""

MCPHttpClientProvider = McpHttpClientProvider
"""Uppercase-acronym alias for :class:`McpHttpClientProvider`."""

MCPRuntimeServerResolver = McpRuntimeServerResolver
"""Uppercase-acronym alias for :class:`McpRuntimeServerResolver`."""

MCPServerAuthConfig = McpServerAuthConfig
"""Uppercase-acronym alias for :class:`McpServerAuthConfig`."""

MCPServerConfig = McpServerConfig
"""Uppercase-acronym alias for :class:`McpServerConfig`."""

MCPTransport = McpTransport
"""Uppercase-acronym alias for :class:`McpTransport`."""

__all__ = [
    "PLUGIN_NAME",
    "AbstractMcpError",
    "DEFAULT_MCP_SEARCH_LIMIT",
    "IMcpHttpClientProvider",
    "IMcpRuntimeServerResolver",
    "LazyMcpToolset",
    "MCP_CALL_TOOL_NAME",
    "MCP_METADATA_KEY",
    "MCP_SERVERS_METADATA_KEY",
    "MCP_SEARCH_TOOLS_NAME",
    "McpCatalogMergeError",
    "MCPClient",
    "McpClient",
    "MCPConfig",
    "McpConfig",
    "MCPHttpClientProvider",
    "McpHttpClientProvider",
    "MCPRuntimeServerResolver",
    "McpRuntimeServerResolver",
    "McpOAuthClientAuthMethod",
    "McpOAuthClientCredentialsConfig",
    "McpResponseError",
    "MCPServerAuthConfig",
    "McpServerAuthConfig",
    "MCPServerConfig",
    "McpServerConfig",
    "McpServerConfigurationError",
    "McpToolDiscoveryError",
    "McpToolInvocationError",
    "MCPTransport",
    "McpTransport",
    "McpTransportError",
    "build_lazy_mcp_descriptors",
    "build_mcp_runner",
    "resolve_http_auth_headers",
]
