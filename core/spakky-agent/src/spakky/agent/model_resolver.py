"""Runtime model resolution for Agent runs."""

from abc import ABC, abstractmethod

from spakky.agent.interfaces.model import IAgentModel
from spakky.agent.inbound import RunAgentInput


class IAgentModelResolver(ABC):
    """Resolve the model adapter used for one Agent run."""

    @abstractmethod
    def resolve_model(
        self,
        agent_instance: object,
        run_input: RunAgentInput | None = None,
    ) -> IAgentModel | None:
        """Return a run-specific model, or ``None`` to use injected fallback."""
        ...
