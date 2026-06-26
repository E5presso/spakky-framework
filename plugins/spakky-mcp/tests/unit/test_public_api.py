"""Tests for spakky-mcp public API exports."""

import spakky.plugins.mcp as mcp_api
from spakky.plugins.mcp import (
    PLUGIN_NAME,
    AbstractMcpError,
    ExternalMcpTool,
    ExternalMcpToolDescriptor,
    IMcpHttpClientProvider,
    IMcpRuntimeServerResolver,
    MCP_METADATA_KEY,
    MCP_SERVERS_METADATA_KEY,
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
    McpToolExposureError,
    McpToolInvocationError,
    McpToolServer,
    MCPServer,
    MCPToolServer,
    MCPToolServerEntry,
    McpToolServerAgent,
    MCPToolServerConfig,
    McpToolServerConfig,
    McpToolServerEntry,
    MCPToolServerNotRegisteredError,
    McpToolServerNotRegisteredError,
    MCPToolServerRegistry,
    McpToolServerRegistry,
    MCPTransport,
    McpTransport,
    McpTransportError,
    build_agent_tool_server,
    build_agent_tools,
    build_external_descriptor,
    build_external_descriptors,
    build_mcp_runner,
    connect_server,
    make_mcp_tool_callable,
    merge_external_catalog,
    normalize_call_result,
    normalize_dispatch_result,
    prefixed_tool_name,
    resolve_http_auth_headers,
    serve_stdio,
    streamable_http_session_manager,
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
    assert MCPToolServerConfig is McpToolServerConfig
    assert McpToolServerConfig is mcp_api.McpToolServerConfig
    assert MCPTransport is McpTransport
    assert McpTransport is mcp_api.McpTransport
    assert McpOAuthClientAuthMethod is mcp_api.McpOAuthClientAuthMethod
    assert McpOAuthClientCredentialsConfig is mcp_api.McpOAuthClientCredentialsConfig


def test_public_api_exposes_tool_server_surface() -> None:
    """The public API exposes the server-side exposure functions and Pod."""
    assert MCPToolServer is McpToolServer
    assert McpToolServer is mcp_api.McpToolServer
    assert MCPServer is mcp_api.MCPServer
    assert McpToolServerAgent is MCPServer
    assert MCPToolServerEntry is McpToolServerEntry
    assert McpToolServerEntry is mcp_api.McpToolServerEntry
    assert MCPToolServerRegistry is McpToolServerRegistry
    assert McpToolServerRegistry is mcp_api.McpToolServerRegistry
    assert build_agent_tool_server is mcp_api.build_agent_tool_server
    assert build_agent_tools is mcp_api.build_agent_tools
    assert normalize_dispatch_result is mcp_api.normalize_dispatch_result
    assert serve_stdio is mcp_api.serve_stdio
    assert streamable_http_session_manager is mcp_api.streamable_http_session_manager
    assert McpToolExposureError is mcp_api.McpToolExposureError


def test_public_api_exposes_client_and_catalog_surface() -> None:
    """The public API exposes the client and catalog-integration functions."""
    assert MCPClient is McpClient
    assert McpClient is mcp_api.McpClient
    assert connect_server is mcp_api.connect_server
    assert make_mcp_tool_callable is mcp_api.make_mcp_tool_callable
    assert build_external_descriptor is mcp_api.build_external_descriptor
    assert build_external_descriptors is mcp_api.build_external_descriptors
    assert build_mcp_runner is mcp_api.build_mcp_runner
    assert merge_external_catalog is mcp_api.merge_external_catalog
    assert normalize_call_result is mcp_api.normalize_call_result
    assert prefixed_tool_name is mcp_api.prefixed_tool_name
    assert ExternalMcpTool is mcp_api.ExternalMcpTool
    assert ExternalMcpToolDescriptor is mcp_api.ExternalMcpToolDescriptor
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
    assert MCPToolServerNotRegisteredError is McpToolServerNotRegisteredError
    assert McpToolServerNotRegisteredError is mcp_api.McpToolServerNotRegisteredError
