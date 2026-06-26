"""Post-processor registering @McpToolServerAgent-marked @Agent Pods."""

from logging import getLogger
from typing import override

from spakky.agent import Agent
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.annotations.pod import Pod
from spakky.core.pod.interfaces.aware.container_aware import IContainerAware
from spakky.core.pod.interfaces.container import IContainer
from spakky.core.pod.interfaces.post_processor import IPostProcessor

from spakky.plugins.mcp.server_registry import McpToolServerRegistry
from spakky.plugins.mcp.stereotypes.mcp_tool_server_agent import McpToolServerAgent

logger = getLogger(__name__)


@Order(0)
@Pod()
class RegisterMcpToolServerAgentsPostProcessor(IPostProcessor, IContainerAware):
    """Registers Pods carrying both @Agent and @McpToolServerAgent."""

    _container: IContainer

    @override
    def set_container(self, container: IContainer) -> None:
        self._container = container

    @staticmethod
    def _unwrap_proxy_type(pod_type: type[object]) -> type[object]:
        """Return the original class when *pod_type* is an AOP dynamic proxy."""
        if pod_type.__name__.endswith(DYNAMIC_PROXY_CLASS_NAME_SUFFIX):
            return pod_type.__bases__[0]
        return pod_type

    @override
    def post_process(self, pod: object) -> object:
        """Register *pod* when it is an MCP tool-server agent."""
        pod_type = self._unwrap_proxy_type(type(pod))
        if not (McpToolServerAgent.exists(pod_type) and Agent.exists(pod_type)):
            return pod
        registry = self._container.get(McpToolServerRegistry)
        registry.register(pod, pod_type, McpToolServerAgent.get(pod_type))
        logger.info("Registered MCP tool-server agent from %s", pod_type.__qualname__)
        return pod
