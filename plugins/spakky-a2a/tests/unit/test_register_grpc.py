"""Tests for declarative A2A gRPC handler registration."""

from unittest.mock import MagicMock

from grpc import GenericRpcHandler
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.container import IContainer
from spakky.plugins.grpc.server_spec import GrpcServerSpec

from spakky.plugins.a2a.post_processors.register_grpc import (
    RegisterA2AGRPCPostProcessor,
)
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible
from tests.unit._sample_agents import ServedPlannerAgent, StubModel


class _A2ASpec:
    def __init__(self, handler: GenericRpcHandler) -> None:
        self.handler = handler
        self.calls: list[str] = []

    def build_grpc_handler_for(self, agent_name: str) -> GenericRpcHandler:
        self.calls.append(agent_name)
        return self.handler


def _processor(
    registry: A2AAgentRegistry,
    grpc_spec: GrpcServerSpec,
    a2a_spec: _A2ASpec,
) -> RegisterA2AGRPCPostProcessor:
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(
        side_effect=lambda key: {
            A2AAgentRegistry: registry,
            A2AAgentServerSpec: a2a_spec,
            GrpcServerSpec: grpc_spec,
        }[key]
    )
    container.get_or_none = MagicMock(
        side_effect=lambda key: grpc_spec if key is GrpcServerSpec else None
    )
    processor = RegisterA2AGRPCPostProcessor()
    processor.set_container(container)
    return processor


def test_grpc_spec_post_process_registers_enabled_entries() -> None:
    """grpc_enabled=True인 A2A entry를 GrpcServerSpec에 등록한다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        A2ACompatible(grpc_enabled=True, grpc_base_url="grpc://planner.local"),
    )
    grpc_spec = GrpcServerSpec()
    handler = MagicMock(spec=GenericRpcHandler)
    a2a_spec = _A2ASpec(handler)

    result = _processor(registry, grpc_spec, a2a_spec).post_process(grpc_spec)

    assert result is grpc_spec
    assert a2a_spec.calls == ["planner"]
    assert grpc_spec.handlers == [handler]


def test_grpc_registration_is_idempotent() -> None:
    """동일 agent gRPC handler는 한 번만 등록된다."""
    registry = A2AAgentRegistry()
    agent = ServedPlannerAgent(StubModel())
    registry.register(
        agent,
        ServedPlannerAgent,
        A2ACompatible(grpc_enabled=True, grpc_base_url="grpc://planner.local"),
    )
    grpc_spec = GrpcServerSpec()
    handler = MagicMock(spec=GenericRpcHandler)
    a2a_spec = _A2ASpec(handler)
    processor = _processor(registry, grpc_spec, a2a_spec)

    processor.post_process(grpc_spec)
    processor.post_process(agent)

    assert a2a_spec.calls == ["planner"]
    assert grpc_spec.handlers == [handler]


def test_grpc_registration_unwraps_dynamic_proxy_agent() -> None:
    """AOP dynamic proxy subclass도 원본 @A2ACompatible marker로 등록된다."""

    class ServedPlannerAgentDynamicProxy(ServedPlannerAgent):
        pass

    ServedPlannerAgentDynamicProxy.__name__ = (
        f"ServedPlannerAgent{DYNAMIC_PROXY_CLASS_NAME_SUFFIX}"
    )
    proxy = ServedPlannerAgentDynamicProxy(StubModel())
    registry = A2AAgentRegistry()
    grpc_spec = GrpcServerSpec()
    handler = MagicMock(spec=GenericRpcHandler)
    a2a_spec = _A2ASpec(handler)
    processor = _processor(registry, grpc_spec, a2a_spec)

    processor.post_process(grpc_spec)
    registry.register(
        proxy,
        ServedPlannerAgent,
        A2ACompatible(grpc_enabled=True, grpc_base_url="grpc://planner.local"),
    )
    processor.post_process(proxy)

    assert a2a_spec.calls == ["planner"]
    assert grpc_spec.handlers == [handler]


def test_grpc_disabled_entries_are_ignored() -> None:
    """grpc_enabled가 꺼진 entry는 GrpcServerSpec에 추가하지 않는다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        A2ACompatible(grpc_enabled=False),
    )
    grpc_spec = GrpcServerSpec()
    handler = MagicMock(spec=GenericRpcHandler)
    a2a_spec = _A2ASpec(handler)

    _processor(registry, grpc_spec, a2a_spec).post_process(grpc_spec)

    assert a2a_spec.calls == []
    assert grpc_spec.handlers == []
