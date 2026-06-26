"""Backward-compatible import for the legacy @McpToolServerAgent marker name."""

from spakky.plugins.mcp.stereotypes.mcp_server import MCPServer

McpToolServerAgent = MCPServer
"""Deprecated alias for :class:`MCPServer`."""

__all__ = ["McpToolServerAgent"]
