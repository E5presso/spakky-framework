"""Post-processor registering @A2ACompatible-marked @Agent Pods."""

from logging import getLogger
from typing import override

from spakky.agent.execution import Agent
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

logger = getLogger(__name__)


@Order(0)
@Pod()
class RegisterA2AAgentServersPostProcessor(IPostProcessor, IContainerAware):
    """Registers Pods carrying both @Agent and @A2ACompatible in the registry."""

    _container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @staticmethod
    def _unwrap_proxy_type(pod_type: type) -> type:
        """Return the original class when *pod_type* is an AOP dynamic proxy.

        ``AspectPostProcessor`` may replace a Pod with a dynamic subclass whose
        name ends with ``@DynamicProxy``; ``__bases__[0]`` recovers the original
        @Agent class carrying the A2A marker.
        """
        if pod_type.__name__.endswith(DYNAMIC_PROXY_CLASS_NAME_SUFFIX):
            return pod_type.__bases__[0]
        return pod_type

    @override
    def post_process(self, pod: object) -> object:
        """Register *pod* when it is an @A2ACompatible-marked @Agent.

        Pods missing either marker are returned unchanged.
        """
        pod_type = self._unwrap_proxy_type(type(pod))
        if not (A2ACompatible.exists(pod_type) and Agent.exists(pod_type)):
            return pod
        registry = self._container.get(A2AAgentRegistry)
        registry.register(pod, pod_type, A2ACompatible.get(pod_type))
        logger.info("Registered A2A agent server from %s", pod_type.__qualname__)
        return pod
