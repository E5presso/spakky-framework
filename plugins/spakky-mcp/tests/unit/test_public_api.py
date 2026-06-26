"""Tests for spakky-mcp public API exports."""

import spakky.plugins.mcp as mcp_api
from spakky.plugins.mcp import (
    PLUGIN_NAME,
    AbstractMcpError,
    ExternalMcpTool,
    ExternalMcpToolDescriptor,
    McpCatalogMergeError,
    McpClient,
    McpConfig,
    McpResponseError,
    McpServerConfig,
    McpServerConfigurationError,
    McpToolDiscoveryError,
    McpToolExposureError,
    McpToolInvocationError,
    McpToolServer,
    McpToolServerAgent,
    McpToolServerConfig,
    McpToolServerEntry,
    McpToolServerNotRegisteredError,
    McpToolServerRegistry,
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
    serve_stdio,
    streamable_http_session_manager,
)


def test_public_api_exposes_plugin_identity() -> None:
    """The public API exposes the plugin id and its config surface."""
    assert PLUGIN_NAME.name == "spakky-mcp"
    assert McpConfig is mcp_api.McpConfig
    assert McpServerConfig is mcp_api.McpServerConfig
    assert McpToolServerConfig is mcp_api.McpToolServerConfig
    assert McpTransport is mcp_api.McpTransport


def test_public_api_exposes_tool_server_surface() -> None:
    """The public API exposes the server-side exposure functions and Pod."""
    assert McpToolServer is mcp_api.McpToolServer
    assert McpToolServerAgent is mcp_api.McpToolServerAgent
    assert McpToolServerEntry is mcp_api.McpToolServerEntry
    assert McpToolServerRegistry is mcp_api.McpToolServerRegistry
    assert build_agent_tool_server is mcp_api.build_agent_tool_server
    assert build_agent_tools is mcp_api.build_agent_tools
    assert normalize_dispatch_result is mcp_api.normalize_dispatch_result
    assert serve_stdio is mcp_api.serve_stdio
    assert streamable_http_session_manager is mcp_api.streamable_http_session_manager
    assert McpToolExposureError is mcp_api.McpToolExposureError


def test_public_api_exposes_client_and_catalog_surface() -> None:
    """The public API exposes the client and catalog-integration functions."""
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


def test_public_api_exposes_error_surface() -> None:
    """The public API exposes the plugin error hierarchy."""
    assert AbstractMcpError is mcp_api.AbstractMcpError
    assert McpServerConfigurationError is mcp_api.McpServerConfigurationError
    assert McpTransportError is mcp_api.McpTransportError
    assert McpToolDiscoveryError is mcp_api.McpToolDiscoveryError
    assert McpToolInvocationError is mcp_api.McpToolInvocationError
    assert McpResponseError is mcp_api.McpResponseError
    assert McpCatalogMergeError is mcp_api.McpCatalogMergeError
    assert McpToolServerNotRegisteredError is mcp_api.McpToolServerNotRegisteredError
