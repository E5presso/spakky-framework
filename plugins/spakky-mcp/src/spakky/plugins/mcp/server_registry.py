"""Registry of @Agent instances exposed as MCP tool servers."""

from dataclasses import dataclass

from spakky.agent import Agent
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.mcp.error import McpToolServerNotRegisteredError
from spakky.plugins.mcp.stereotypes.mcp_server import MCPServer


@dataclass(frozen=True, slots=True)
class McpToolServerEntry:
    """A discovered @Agent instance paired with MCP server metadata."""

    instance: object
    agent_type: type[object]
    metadata: MCPServer

    @property
    def agent_name(self) -> str:
        """Return the stable registry name for the agent."""
        agent = Agent.get(self.agent_type)
        return agent.spec.name or self.agent_type.__name__


@Pod()
class McpToolServerRegistry:
    """Holds MCP-exposed @Agent instances keyed by agent name."""

    _entries: dict[str, McpToolServerEntry]

    def __init__(self) -> None:
        self._entries = {}

    def register(
        self,
        instance: object,
        agent_type: type[object],
        metadata: MCPServer,
    ) -> McpToolServerEntry:
        """Register one MCP server entry and return it."""
        entry = McpToolServerEntry(
            instance=instance,
            agent_type=agent_type,
            metadata=metadata,
        )
        self._entries[entry.agent_name] = entry
        return entry

    def get(self, agent_name: str) -> McpToolServerEntry:
        """Return the entry for ``agent_name``."""
        entry = self._entries.get(agent_name)
        if entry is None:
            raise McpToolServerNotRegisteredError(agent_name)
        return entry

    def list_entries(self) -> tuple[McpToolServerEntry, ...]:
        """Return registered entries in stable name order."""
        return tuple(self._entries[name] for name in sorted(self._entries))
