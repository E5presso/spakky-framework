"""Post-processor registering A2A gRPC handlers with spakky-grpc."""

from typing import cast, override

from spakky.agent.execution import Agent
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

GRPC_SERVER_SPEC_MODULE = "spakky.plugins.grpc.server_spec"
"""Module path used to identify spakky-grpc's GrpcServerSpec without importing it."""

GRPC_SERVER_SPEC_NAME = "GrpcServerSpec"
"""Class name used to identify spakky-grpc's GrpcServerSpec without importing it."""


class _GrpcServerSpecLike:
    """Nominal local type for the GrpcServerSpec method this adapter needs."""

    def add_handler(self, handler: object) -> None:
        """Register a generic RPC handler."""
        ...


@Order(2)
@Pod()
class RegisterA2AGRPCPostProcessor(IPostProcessor, IContainerAware):
    """Register @A2ACompatible gRPC handlers when spakky-grpc is active."""

    _container: IContainer
    _registered: set[str]
    _grpc_specs: list[_GrpcServerSpecLike]

    def __init__(self) -> None:
        self._registered = set()
        self._grpc_specs = []

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @staticmethod
    def _unwrap_proxy_type(pod_type: type[object]) -> type[object]:
        """Return the original class when *pod_type* is an AOP dynamic proxy."""
        if pod_type.__name__.endswith(DYNAMIC_PROXY_CLASS_NAME_SUFFIX):
            return pod_type.__bases__[0]
        return pod_type

    @staticmethod
    def _is_grpc_spec(pod: object) -> bool:
        pod_type = type(pod)
        return (
            pod_type.__module__ == GRPC_SERVER_SPEC_MODULE
            and pod_type.__name__ == GRPC_SERVER_SPEC_NAME
        )

    @override
    def post_process(self, pod: object) -> object:
        """Register enabled A2A gRPC handlers when a spec or agent appears."""
        if self._is_grpc_spec(pod):
            grpc_spec = cast(_GrpcServerSpecLike, pod)
            self._grpc_specs.append(grpc_spec)
            for entry in self._container.get(A2AAgentRegistry).list_entries():
                self._register_entry(grpc_spec, entry.agent_name)
            return pod
        if self._is_marked_agent(pod):
            agent_type = self._unwrap_proxy_type(type(pod))
            agent_name = self._agent_name(agent_type)
            for grpc_spec in self._grpc_specs:
                self._register_entry(grpc_spec, agent_name)
        return pod

    def _is_marked_agent(self, pod: object) -> bool:
        agent_type = self._unwrap_proxy_type(type(pod))
        return A2ACompatible.exists(agent_type) and Agent.exists(agent_type)

    def _register_entry(self, grpc_spec: _GrpcServerSpecLike, agent_name: str) -> None:
        entry = self._container.get(A2AAgentRegistry).get(agent_name)
        if not entry.metadata.grpc_enabled:
            return
        if entry.agent_name in self._registered:
            return
        a2a_spec = self._container.get(A2AAgentServerSpec)
        grpc_spec.add_handler(a2a_spec.build_grpc_handler_for(entry.agent_name))
        self._registered.add(entry.agent_name)

    @staticmethod
    def _agent_name(agent_type: type[object]) -> str:
        agent = Agent.get(agent_type)
        return agent.spec.name or agent_type.__name__
