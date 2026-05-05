"""Bootstrap validation for Agent Pod instances."""

from typing import NoReturn, override

from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.agent.error import (
    AgentBootstrapError,
    AgentDefinitionError,
    AgentPersistenceConfigurationError,
)
from spakky.agent.execution import Agent


@Pod()
class AgentBootstrapValidationPostProcessor(IPostProcessor, IContainerAware):
    """Validate Agent metadata during application bootstrap."""

    _container: IContainer | None

    def __init__(self) -> None:
        """Initialize without assuming application context injection happened."""
        self._container = None

    @override
    def set_container(self, container: IContainer) -> None:
        """Receive the active container for contribution validation."""
        self._container = container

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
        self._validate_persistence_contributions(agent)
        return pod

    def _validate_persistence_contributions(self, agent: Agent) -> None:
        required_types = agent.required_persistence_repository_types()
        if len(required_types) == 0:
            return
        container = self._container
        if container is None:
            self._raise_missing_persistence(agent, required_types)
        missing_types = tuple(
            repository_type
            for repository_type in required_types
            if not container.contains(repository_type)
        )
        if len(missing_types) > 0:
            self._raise_missing_persistence(agent, missing_types)

    def _raise_missing_persistence(
        self,
        agent: Agent,
        missing_types: tuple[type[object], ...],
    ) -> NoReturn:
        agent_name = self._agent_type_name(agent)
        repository_names = ", ".join(
            repository_type.__name__ for repository_type in missing_types
        )
        raise AgentPersistenceConfigurationError(
            "Agent persistence contribution is required for "
            f"{agent_name}. Missing repositories: {repository_names}. "
            "Install/activate provider contribution: spakky-sqlalchemy[agent] "
            "via spakky.contributions.spakky.agent."
        )

    def _agent_type_name(self, agent: Agent) -> str:
        target = agent.target
        if isinstance(target, type):
            return target.__name__
        return str(target)
