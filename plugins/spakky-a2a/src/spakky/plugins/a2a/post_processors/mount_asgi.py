"""Post-processor that mounts discovered A2A agents on ASGI host Pods."""

from logging import getLogger
from typing import cast, override

from spakky.agent.execution import Agent
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from starlette.applications import Starlette

from spakky.plugins.a2a.error import A2AEndpointConflictError
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry, A2AAgentServerEntry
from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer

logger = getLogger(__name__)


@Order(1)
@Pod()
class MountA2AASGIPostProcessor(
    IPostProcessor, IContainerAware, IApplicationContextAware
):
    """Mount registered A2A agent apps on Starlette-compatible host Pods."""

    _container: IContainer
    _application_context: IApplicationContext
    _claimed_paths: dict[tuple[int, str], str]
    _mounted: set[tuple[int, str]]

    def __init__(self) -> None:
        self._claimed_paths = {}
        self._mounted = set()

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        self._application_context = application_context

    @staticmethod
    def _unwrap_proxy_type(pod_type: type[object]) -> type[object]:
        """Return the original class when *pod_type* is an AOP dynamic proxy."""
        if pod_type.__name__.endswith(DYNAMIC_PROXY_CLASS_NAME_SUFFIX):
            return pod_type.__bases__[0]
        return pod_type

    @override
    def post_process(self, pod: object) -> object:
        """Mount registered A2A servers when a host or marked agent appears."""
        if isinstance(pod, Starlette):
            self._mount_registered_agents(pod)
            return pod
        agent_type = self._unwrap_proxy_type(type(pod))
        if not (A2AAgentServer.exists(agent_type) and Agent.exists(agent_type)):
            return pod
        entry = self._container.get(A2AAgentRegistry).get(self._agent_name(agent_type))
        for app in self._asgi_hosts():
            self._mount_entry(app, entry)
        logger.info("Mounted A2A agent server from %s", agent_type.__qualname__)
        return pod

    def _asgi_hosts(self) -> tuple[Starlette, ...]:
        """Return all Starlette-compatible host application Pods."""
        return tuple(
            cast(Starlette, app)
            for app in self._application_context.find(
                lambda pod: pod.type_ is Starlette or Starlette in pod.base_types
            )
        )

    def _mount_registered_agents(self, app: Starlette) -> None:
        registry = self._container.get(A2AAgentRegistry)
        for entry in registry.list_entries():
            self._mount_entry(app, entry)

    def _mount_entry(self, app: Starlette, entry: A2AAgentServerEntry) -> None:
        spec = self._container.get(A2AAgentServerSpec)
        path = spec.mount_path_for(entry.agent_name)
        app_id = id(app)
        claim_key = (app_id, path)
        current_agent = self._claimed_paths.get(claim_key)
        if current_agent is not None and current_agent != entry.agent_name:
            raise A2AEndpointConflictError
        self._claimed_paths[claim_key] = entry.agent_name
        mount_key = (app_id, entry.agent_name)
        if mount_key in self._mounted:
            return
        app.mount(path, spec.build_app_for(entry.agent_name))
        self._mounted.add(mount_key)

    @staticmethod
    def _agent_name(agent_type: type[object]) -> str:
        agent = Agent.get(agent_type)
        return agent.spec.name or agent_type.__name__
