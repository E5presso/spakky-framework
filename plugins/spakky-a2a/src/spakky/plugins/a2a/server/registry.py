"""Registry of @Agent instances exposed as A2A servers."""

from dataclasses import dataclass

from spakky.agent.execution import Agent
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.a2a.error import A2AAgentServerNotRegisteredError
from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer


@dataclass(frozen=True, slots=True)
class A2AAgentServerEntry:
    """A discovered @Agent instance paired with its A2A transport metadata."""

    instance: object
    metadata: A2AAgentServer


@Pod()
class A2AAgentRegistry:
    """Holds the @Agent instances discovered as A2A servers, keyed by name."""

    _entries: dict[str, A2AAgentServerEntry]

    def __init__(self) -> None:
        self._entries = {}

    def register(self, instance: object, metadata: A2AAgentServer) -> None:
        """Register an @Agent instance under its resolved agent name.

        Args:
            instance: The @Agent Pod instance to serve.
            metadata: The A2A transport metadata declared on the agent class.
        """
        self._entries[self._agent_name(instance)] = A2AAgentServerEntry(
            instance=instance,
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

    @staticmethod
    def _agent_name(instance: object) -> str:
        """Resolve an agent's registry name from its spec name or class name."""
        agent = Agent.get(type(instance))
        return agent.spec.name or type(instance).__name__
