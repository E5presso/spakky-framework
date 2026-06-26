"""Assembly of a mountable A2A ASGI application for one @Agent instance.

The a2a-sdk 1.x server is assembled from route factories rather than a single
application class: the agent-card route plus the JSON-RPC routes (with v0.3
compatibility enabling the ``message/send`` / ``tasks/get`` method names) are
mounted on a Starlette app the host application can further mount.
"""

from typing import override

from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.utils import DEFAULT_RPC_URL
from spakky.agent.execution import Agent
from spakky.agent.runner_factory import IAgentRunnerFactory
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from starlette.applications import Starlette

from spakky.plugins.a2a.card.derivation import AgentCardFactory
from spakky.plugins.a2a.config import A2AConfig
from spakky.plugins.a2a.grpc_transport.builder import build_a2a_grpc_handler
from spakky.plugins.a2a.grpc_transport.handler import A2AGrpcHandler
from spakky.plugins.a2a.rest_transport.builder import build_a2a_rest_app
from spakky.plugins.a2a.server.request_handler import build_a2a_request_handler
from spakky.plugins.a2a.server.registry import A2AAgentServerEntry
from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository


def build_a2a_app(
    agent_instance: object,
    *,
    base_url: str,
    version: str,
    repository: IA2ATaskRepository | None = None,
    agent_type: type[object] | None = None,
    runner_factory: IAgentRunnerFactory | None = None,
) -> Starlette:
    """Assemble a mountable A2A ASGI application for an @Agent instance.

    Args:
        agent_instance: The @Agent Pod instance to serve.
        base_url: Transport endpoint advertised on the derived AgentCard.
        version: Semantic version advertised on the derived AgentCard.
        repository: Task persistence port; an in-memory store is used when None.
        agent_type: Original @Agent class, supplied when the instance is proxied.

    Returns:
        A Starlette application exposing the agent-card and JSON-RPC routes.
    """
    card = AgentCardFactory().build(
        Agent.get(agent_type or type(agent_instance)),
        base_url,
        version,
    )
    handler = build_a2a_request_handler(
        agent_instance,
        base_url=base_url,
        version=version,
        repository=repository,
        agent_type=agent_type,
        card=card,
        runner_factory=runner_factory,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, DEFAULT_RPC_URL, enable_v0_3_compat=True),
    ]
    return Starlette(routes=routes)


@Pod()
class A2AAgentServerSpec(IContainerAware):
    """Container-aware factory that builds A2A apps for registered agents."""

    _container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    def build_app_for(self, agent_name: str) -> Starlette:
        """Build a mountable A2A app for a registered agent name.

        Resolves the registry entry, then an optional task repository Pod from the
        container, falling back to an in-memory store when none is registered.

        Args:
            agent_name: The registered agent name to serve.

        Returns:
            A Starlette application for the named agent.
        """
        entry = self._container.get(A2AAgentRegistry).get(agent_name)
        # Repository Pod is optional; absent one, persistence stays in-process.
        repository = self._container.get_or_none(IA2ATaskRepository)
        runner_factory = self._container.get(IAgentRunnerFactory)
        return build_a2a_app(
            entry.instance,
            base_url=self._base_url(entry),
            version=self._version(entry),
            repository=repository,
            agent_type=entry.agent_type,
            runner_factory=runner_factory,
        )

    def build_rest_app_for(self, agent_name: str) -> Starlette:
        """Build a mountable A2A REST app for a registered agent name."""
        entry = self._container.get(A2AAgentRegistry).get(agent_name)
        repository = self._container.get_or_none(IA2ATaskRepository)
        runner_factory = self._container.get(IAgentRunnerFactory)
        return build_a2a_rest_app(
            entry.instance,
            base_url=self._rest_base_url(entry),
            version=self._version(entry),
            repository=repository,
            agent_type=entry.agent_type,
            runner_factory=runner_factory,
        )

    def build_grpc_handler_for(self, agent_name: str) -> A2AGrpcHandler:
        """Build an A2A gRPC handler for a registered agent name."""
        entry = self._container.get(A2AAgentRegistry).get(agent_name)
        repository = self._container.get_or_none(IA2ATaskRepository)
        runner_factory = self._container.get(IAgentRunnerFactory)
        return build_a2a_grpc_handler(
            entry.instance,
            base_url=self._grpc_base_url(entry),
            version=self._version(entry),
            repository=repository,
            agent_type=entry.agent_type,
            runner_factory=runner_factory,
        )

    def mount_path_for(self, agent_name: str) -> str:
        """Return the ASGI mount path for a registered agent."""
        entry = self._container.get(A2AAgentRegistry).get(agent_name)
        if entry.metadata.mount_path is not None:
            return entry.metadata.mount_path
        prefix = self._config().default_mount_path_prefix.rstrip("/")
        return f"{prefix}/{agent_name}"

    def rest_mount_path_for(self, agent_name: str) -> str | None:
        """Return the optional REST ASGI mount path for a registered agent."""
        entry = self._container.get(A2AAgentRegistry).get(agent_name)
        return entry.metadata.rest_mount_path

    def _base_url(self, entry: A2AAgentServerEntry) -> str:
        if entry.metadata.base_url is not None:
            return entry.metadata.base_url
        default_host = self._config().default_base_url.rstrip("/")
        return f"{default_host}{self.mount_path_for(entry.agent_name)}"

    def _rest_base_url(self, entry: A2AAgentServerEntry) -> str:
        if entry.metadata.rest_base_url is not None:
            return entry.metadata.rest_base_url
        rest_mount_path = entry.metadata.rest_mount_path
        if rest_mount_path is not None:
            return f"{self._config().default_base_url.rstrip('/')}{rest_mount_path}"
        return self._base_url(entry)

    def _grpc_base_url(self, entry: A2AAgentServerEntry) -> str:
        if entry.metadata.grpc_base_url is not None:
            return entry.metadata.grpc_base_url
        return self._base_url(entry)

    def _version(self, entry: A2AAgentServerEntry) -> str:
        return entry.metadata.version or self._config().default_version

    def _config(self) -> A2AConfig:
        return self._container.get(A2AConfig)
