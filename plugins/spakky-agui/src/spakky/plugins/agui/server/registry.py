"""Registry of @Agent instances exposed through AG-UI transports."""

from dataclasses import dataclass

from spakky.agent import Agent
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.agui.error import AgUiRunResolutionError
from spakky.plugins.agui.stereotypes.agui_agent import AgUiAgent


@dataclass(frozen=True, slots=True)
class AgUiAgentEntry:
    """A discovered @Agent instance paired with its AG-UI metadata."""

    instance: object
    agent_type: type[object]
    metadata: AgUiAgent

    @property
    def agent_name(self) -> str:
        """Return the stable AG-UI agent id."""
        agent = Agent.get(self.agent_type)
        return agent.spec.name or self.agent_type.__name__


@Pod()
class AgUiAgentRegistry:
    """Holds AG-UI-exposed @Agent instances keyed by agent name."""

    _entries: dict[str, AgUiAgentEntry]

    def __init__(self) -> None:
        self._entries = {}

    def register(
        self,
        instance: object,
        agent_type: type[object],
        metadata: AgUiAgent,
    ) -> AgUiAgentEntry:
        """Register one exposed @Agent instance and return the entry."""
        entry = AgUiAgentEntry(
            instance=instance,
            agent_type=agent_type,
            metadata=metadata,
        )
        self._entries[entry.agent_name] = entry
        return entry

    def get(self, agent_name: str) -> AgUiAgentEntry:
        """Return the entry for ``agent_name``."""
        entry = self._entries.get(agent_name)
        if entry is None:
            raise AgUiRunResolutionError
        return entry

    def list_entries(self) -> tuple[AgUiAgentEntry, ...]:
        """Return registered AG-UI agent entries in stable name order."""
        return tuple(self._entries[name] for name in sorted(self._entries))
