"""Registry of @Agent instances exposed as A2A servers."""

from dataclasses import dataclass

from spakky.agent.execution import Agent
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.a2a.error import A2AAgentServerNotRegisteredError
from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible


@dataclass(frozen=True, slots=True)
class A2AAgentServerEntry:
    """A discovered @Agent instance paired with its A2A transport metadata."""

    agent_name: str
    instance: object
    agent_type: type[object]
    metadata: A2ACompatible


@Pod()
class A2AAgentRegistry:
    """Holds the @Agent instances discovered as A2A servers, keyed by name."""

    _entries: dict[str, A2AAgentServerEntry]

    def __init__(self) -> None:
        self._entries = {}

    def register(
        self,
        instance: object,
        agent_type: type[object],
        metadata: A2ACompatible,
    ) -> None:
        """Register an @Agent instance under its resolved agent name.

        Args:
            instance: The @Agent Pod instance to serve.
            agent_type: The original @Agent type, unwrapped from AOP proxies.
            metadata: The A2A transport metadata declared on the agent class.
        """
        agent_name = self._agent_name(agent_type)
        self._entries[agent_name] = A2AAgentServerEntry(
            agent_name=agent_name,
            instance=instance,
            agent_type=agent_type,
            metadata=metadata,
        )

    def get(self, agent_name: str) -> A2AAgentServerEntry:
        """Return the registered entry for an agent name.

        Raises:
            A2AAgentServerNotRegisteredError: No entry exists for the name.
        """
        entry = self._entries.get(agent_name)
        if entry is None:
            raise A2AAgentServerNotRegisteredError(agent_name)
        return entry

    def list_entries(self) -> tuple[A2AAgentServerEntry, ...]:
        """Return registered A2A agent entries in stable name order."""
        return tuple(self._entries[name] for name in sorted(self._entries))

    @staticmethod
    def _agent_name(agent_type: type[object]) -> str:
        """Resolve an agent's registry name from its spec name or class name."""
        agent = Agent.get(agent_type)
        return agent.spec.name or agent_type.__name__
