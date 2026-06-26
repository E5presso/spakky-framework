"""Tests for registering @McpToolServerAgent Pods."""

from unittest.mock import MagicMock

import pytest
from spakky.agent import Agent, AgentExecutionSpec
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.mcp.error import McpToolServerNotRegisteredError
from spakky.plugins.mcp.post_processors.register_tool_server_agents import (
    RegisterMcpToolServerAgentsPostProcessor,
)
from spakky.plugins.mcp.server_registry import McpToolServerRegistry
from tests.unit.test_server import ToolAgent


@Agent(spec=AgentExecutionSpec(name="plain", objective="plain"))
class _PlainAgent:
    """An @Agent without the MCP tool-server marker."""

    def __init__(self) -> None:
        self.ready = True


@pytest.fixture
def registry() -> McpToolServerRegistry:
    """Provide a fresh registry."""
    return McpToolServerRegistry()


@pytest.fixture
def processor(
    registry: McpToolServerRegistry,
) -> RegisterMcpToolServerAgentsPostProcessor:
    """Wire the post-processor to a registry-returning container."""
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    processor = RegisterMcpToolServerAgentsPostProcessor()
    processor.set_container(container)
    return processor


def test_registers_marked_agent_pod(
    processor: RegisterMcpToolServerAgentsPostProcessor,
    registry: McpToolServerRegistry,
) -> None:
    """@McpToolServerAgent @Agent Pod가 registry에 등록된다."""
    pod = ToolAgent()

    result = processor.post_process(pod)

    assert result is pod
    assert registry.get("unit").instance is pod
    assert registry.get("unit").metadata.server_name == "marked-agent"


def test_ignores_unmarked_agent_pod(
    processor: RegisterMcpToolServerAgentsPostProcessor,
    registry: McpToolServerRegistry,
) -> None:
    """MCP marker 없는 @Agent Pod는 등록하지 않는다."""
    pod = _PlainAgent()

    result = processor.post_process(pod)

    assert result is pod
    with pytest.raises(McpToolServerNotRegisteredError):
        registry.get("plain")


def test_ignores_plain_object(
    processor: RegisterMcpToolServerAgentsPostProcessor,
) -> None:
    """@Agent가 아닌 object는 그대로 반환한다."""
    pod = object()

    assert processor.post_process(pod) is pod


def test_unwraps_dynamic_proxy_type_before_registering(
    processor: RegisterMcpToolServerAgentsPostProcessor,
    registry: McpToolServerRegistry,
) -> None:
    """AOP dynamic proxy subclass는 원본 marker 기준으로 등록된다."""

    class ToolAgentDynamicProxy(ToolAgent):
        marker = "proxy"

    ToolAgentDynamicProxy.__name__ = f"ToolAgent{DYNAMIC_PROXY_CLASS_NAME_SUFFIX}"
    proxy = ToolAgentDynamicProxy()

    result = processor.post_process(proxy)

    assert result is proxy
    assert registry.get("unit").instance is proxy
