"""Tests for spakky-mcp public API exports."""

import spakky.plugins.mcp as mcp_api
from spakky.plugins.mcp import (
    PLUGIN_NAME,
    AbstractMcpError,
    DEFAULT_MCP_SEARCH_LIMIT,
    IMcpHttpClientProvider,
    IMcpRuntimeServerResolver,
    LazyMcpToolset,
    MCP_CALL_TOOL_NAME,
    MCP_METADATA_KEY,
    MCP_SERVERS_METADATA_KEY,
    MCP_SEARCH_TOOLS_NAME,
    McpCatalogMergeError,
    MCPClient,
    McpClient,
    MCPConfig,
    McpConfig,
    MCPHttpClientProvider,
    McpHttpClientProvider,
    McpOAuthClientAuthMethod,
    McpOAuthClientCredentialsConfig,
    McpResponseError,
    MCPRuntimeServerResolver,
    McpRuntimeServerResolver,
    MCPServerAuthConfig,
    McpServerAuthConfig,
    MCPServerConfig,
    McpServerConfig,
    McpServerConfigurationError,
    McpToolDiscoveryError,
    McpToolInvocationError,
    MCPTransport,
    McpTransport,
    McpTransportError,
    build_lazy_mcp_descriptors,
    build_mcp_runner,
    resolve_http_auth_headers,
)


def test_public_api_exposes_plugin_identity() -> None:
    """The public API exposes the plugin id and its config surface."""
    assert PLUGIN_NAME.name == "spakky-mcp"
    assert MCPConfig is McpConfig
    assert McpConfig is mcp_api.McpConfig
    assert MCPServerConfig is McpServerConfig
    assert McpServerConfig is mcp_api.McpServerConfig
    assert MCPServerAuthConfig is McpServerAuthConfig
    assert McpServerAuthConfig is mcp_api.McpServerAuthConfig
    assert MCPTransport is McpTransport
    assert McpTransport is mcp_api.McpTransport
    assert McpOAuthClientAuthMethod is mcp_api.McpOAuthClientAuthMethod
    assert McpOAuthClientCredentialsConfig is mcp_api.McpOAuthClientCredentialsConfig


def test_public_api_exposes_client_and_catalog_surface() -> None:
    """The public API exposes the client and catalog-integration functions."""
    assert MCPClient is McpClient
    assert McpClient is mcp_api.McpClient
    assert build_lazy_mcp_descriptors is mcp_api.build_lazy_mcp_descriptors
    assert build_mcp_runner is mcp_api.build_mcp_runner
    assert LazyMcpToolset is mcp_api.LazyMcpToolset
    assert MCP_SEARCH_TOOLS_NAME == "mcp_search_tools"
    assert MCP_CALL_TOOL_NAME == "mcp_call_tool"
    assert DEFAULT_MCP_SEARCH_LIMIT == 20
    assert IMcpHttpClientProvider is mcp_api.IMcpHttpClientProvider
    assert MCPHttpClientProvider is McpHttpClientProvider
    assert McpHttpClientProvider is mcp_api.McpHttpClientProvider
    assert IMcpRuntimeServerResolver is mcp_api.IMcpRuntimeServerResolver
    assert MCPRuntimeServerResolver is McpRuntimeServerResolver
    assert McpRuntimeServerResolver is mcp_api.McpRuntimeServerResolver
    assert MCP_METADATA_KEY == "mcp"
    assert MCP_SERVERS_METADATA_KEY == "servers"
    assert resolve_http_auth_headers is mcp_api.resolve_http_auth_headers


def test_public_api_exposes_error_surface() -> None:
    """The public API exposes the plugin error hierarchy."""
    assert AbstractMcpError is mcp_api.AbstractMcpError
    assert McpServerConfigurationError is mcp_api.McpServerConfigurationError
    assert McpTransportError is mcp_api.McpTransportError
    assert McpToolDiscoveryError is mcp_api.McpToolDiscoveryError
    assert McpToolInvocationError is mcp_api.McpToolInvocationError
    assert McpResponseError is mcp_api.McpResponseError
    assert McpCatalogMergeError is mcp_api.McpCatalogMergeError
