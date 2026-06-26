"""@AgUiAgent marker for exposing an @Agent over AG-UI transports."""

from dataclasses import dataclass

from spakky.core.pod.annotations.tag import Tag


@dataclass(eq=False)
class AgUiAgent(Tag):
    """Marks an @Agent class to be served through the AG-UI adapter.

    Paths default to :class:`AgUiConfig` so a single declaration can use the
    plugin defaults, while multi-agent applications can assign distinct paths
    declaratively on each marked agent.
    """

    sse_path: str | None = None
    """SSE endpoint path for this agent. None uses ``AgUiConfig.sse_path``."""

    http_stream_path: str | None = None
    """HTTP streaming endpoint path. None uses ``AgUiConfig.http_stream_path``."""

    websocket_path: str | None = None
    """WebSocket endpoint path. None uses ``AgUiConfig.websocket_path``."""

    server_names: tuple[str, ...] = ()
    """External MCP server names to join for this agent. Empty means all configured."""
