"""Bootstrap validation for Agent Pod instances."""

from typing import override

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.agent.error import AgentBootstrapError, AgentDefinitionError
from spakky.agent.execution import Agent


@Pod()
class AgentBootstrapValidationPostProcessor(IPostProcessor):
    """Validate Agent metadata during application bootstrap."""

    @override
    def post_process(self, pod: object) -> object:
        """Fail startup when an Agent contract is no longer valid."""
        agent = Agent.get_or_none(type(pod))
        if agent is None:
            return pod
        try:
            agent.validate_bootstrap()
        except AgentDefinitionError as e:
            raise AgentBootstrapError("Agent bootstrap contract is invalid") from e
        return pod
