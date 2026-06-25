"""Error classes for the spakky-mcp client plugin."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractMcpError(AbstractSpakkyFrameworkError, ABC):
    """Base class for MCP client adapter errors."""

    ...


class McpServerConfigurationError(AbstractMcpError):
    """Raised when an external MCP server declaration is invalid."""

    message = "MCP server configuration is invalid"


class McpTransportError(AbstractMcpError):
    """Raised when an external MCP server connection cannot be established."""

    message = "MCP server connection failed"


class McpToolDiscoveryError(AbstractMcpError):
    """Raised when tool discovery against an MCP server fails."""

    message = "MCP tool discovery failed"


class McpToolInvocationError(AbstractMcpError):
    """Raised when an external MCP tool call fails or reports an error result."""

    message = "MCP tool invocation failed"


class McpResponseError(AbstractMcpError):
    """Raised when an MCP tool result cannot be mapped to a JSON value."""

    message = "MCP tool result is invalid"


class McpCatalogMergeError(AbstractMcpError):
    """Raised when an external MCP tool collides with an existing catalog tool."""

    message = "MCP tool collides with an existing catalog tool"
