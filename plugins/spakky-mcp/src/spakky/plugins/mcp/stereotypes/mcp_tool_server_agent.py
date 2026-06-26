"""@McpToolServerAgent marker for exposing an @Agent's tools over MCP."""

from dataclasses import dataclass

from spakky.core.pod.annotations.tag import Tag


@dataclass(eq=False)
class McpToolServerAgent(Tag):
    """Marks an @Agent class whose native tools are exposed through MCP."""

    server_name: str | None = None
    """MCP server identity. None uses ``McpConfig.tool_server.name``."""
