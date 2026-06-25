"""Tests for the @A2AAgentServer registration post-processor."""

from unittest.mock import MagicMock

import pytest
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.a2a.error import A2AAgentServerNotRegisteredError
from spakky.plugins.a2a.post_processors.register_agent_servers import (
    RegisterA2AAgentServersPostProcessor,
)
from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from tests.unit._sample_agents import (
    ServedPlannerAgent,
    StubModel,
    UnservedAgent,
)


@pytest.fixture
def registry() -> A2AAgentRegistry:
    """Provide a fresh registry per test."""
    return A2AAgentRegistry()


@pytest.fixture
def processor(registry: A2AAgentRegistry) -> RegisterA2AAgentServersPostProcessor:
    """Provide a processor wired to a container returning the registry."""
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    processor = RegisterA2AAgentServersPostProcessor()
    processor.set_container(container)
    return processor


def test_registers_marked_agent_pod(
    processor: RegisterA2AAgentServersPostProcessor,
    registry: A2AAgentRegistry,
) -> None:
    """A Pod with both @Agent and @A2AAgentServer is registered by name."""
    pod = ServedPlannerAgent(StubModel())

    result = processor.post_process(pod)

    assert result is pod
    entry = registry.get("planner")
    assert entry.instance is pod
    assert entry.metadata.base_url == "http://planner.local"


def test_ignores_agent_without_marker(
    processor: RegisterA2AAgentServersPostProcessor,
    registry: A2AAgentRegistry,
) -> None:
    """An @Agent Pod lacking the A2A marker is returned unchanged and unregistered."""
    pod = UnservedAgent(StubModel())

    result = processor.post_process(pod)

    assert result is pod
    with pytest.raises(A2AAgentServerNotRegisteredError):
        registry.get("unserved")


def test_ignores_non_agent_pod(
    processor: RegisterA2AAgentServersPostProcessor,
) -> None:
    """A plain Pod that is neither agent nor marker is returned unchanged."""

    class PlainPod:
        pass

    pod = PlainPod()

    assert processor.post_process(pod) is pod


def test_unwraps_aop_proxy_type_before_registering(
    processor: RegisterA2AAgentServersPostProcessor,
    registry: A2AAgentRegistry,
) -> None:
    """A dynamic AOP proxy subclass is unwrapped to find the marked base class."""

    class ServedPlannerAgent_DynamicProxy(ServedPlannerAgent):
        pass

    ServedPlannerAgent_DynamicProxy.__name__ = (
        f"ServedPlannerAgent{DYNAMIC_PROXY_CLASS_NAME_SUFFIX}"
    )
    proxy = ServedPlannerAgent_DynamicProxy(StubModel())

    result = processor.post_process(proxy)

    assert result is proxy
    assert registry.get("planner").instance is proxy
