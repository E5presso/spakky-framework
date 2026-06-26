"""Error classes for the spakky-mcp adapter (external clients and tool server)."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractMcpError(AbstractSpakkyFrameworkError, ABC):
    """Base class for MCP adapter errors (external client and tool server)."""

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


class McpToolExposureError(AbstractMcpError):
    """Raised when dispatching an inbound MCP tool call against the agent fails."""

    message = "MCP tool call dispatch failed"


class McpToolServerNotRegisteredError(AbstractMcpError):
    """Raised when no MCP tool-server agent exists for a requested name."""

    message = "No MCP tool-server agent is registered for the agent name"

    def __init__(self, agent_name: str) -> None:
        super().__init__()
        self.agent_name = agent_name
