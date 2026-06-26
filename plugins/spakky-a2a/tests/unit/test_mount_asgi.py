"""Tests for declarative A2A ASGI auto-mounting."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer
from starlette.applications import Starlette

from spakky.plugins.a2a.error import A2AEndpointConflictError
from spakky.plugins.a2a.post_processors.mount_asgi import MountA2AASGIPostProcessor
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from tests.unit._sample_agents import ServedPlannerAgent, StubModel, UnservedAgent


@dataclass(frozen=True, slots=True)
class _PodRecord:
    type_: type[object]
    base_types: tuple[type[object], ...]


class _ApplicationContext:
    def __init__(self, pods: tuple[tuple[object, _PodRecord], ...]) -> None:
        self._pods = pods

    def find(self, selector: Callable[[_PodRecord], bool]) -> set[object]:
        return {instance for instance, record in self._pods if selector(record)}


class _Container:
    def __init__(
        self,
        registry: A2AAgentRegistry,
        spec: object,
    ) -> None:
        self._registry = registry
        self._spec = spec

    def get(self, type_: type[object]) -> object:
        if type_ is A2AAgentRegistry:
            return self._registry
        return self._spec


class _ServerSpec:
    def __init__(
        self,
        mount_path: str = "/a2a/planner",
        rest_mount_path: str | None = None,
    ) -> None:
        self.builds: list[str] = []
        self.rest_builds: list[str] = []
        self.mount_path = mount_path
        self.rest_mount_path = rest_mount_path

    def mount_path_for(self, agent_name: str) -> str:
        return self.mount_path

    def rest_mount_path_for(self, agent_name: str) -> str | None:
        return self.rest_mount_path

    def build_app_for(self, agent_name: str) -> Starlette:
        self.builds.append(agent_name)
        return Starlette()

    def build_rest_app_for(self, agent_name: str) -> Starlette:
        self.rest_builds.append(agent_name)
        return Starlette()


def _processor(
    registry: A2AAgentRegistry,
    spec: _ServerSpec,
    host: Starlette | None = None,
) -> MountA2AASGIPostProcessor:
    processor = MountA2AASGIPostProcessor()
    processor.set_container(
        cast(IContainer, _Container(registry, cast(A2AAgentServerSpec, spec)))
    )
    pods: tuple[tuple[object, _PodRecord], ...] = ()
    if host is not None:
        pods = ((host, _PodRecord(type_=Starlette, base_types=())),)
    processor.set_application_context(
        cast(IApplicationContext, _ApplicationContext(pods))
    )
    return processor


def test_starlette_host_post_process_mounts_registered_agents() -> None:
    """ASGI host Pod가 처리될 때 registry의 A2A agent app이 mount된다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()), ServedPlannerAgent, _planner_marker()
    )
    spec = _ServerSpec()
    host = Starlette()

    processed = _processor(registry, spec).post_process(host)

    assert processed is host
    assert spec.builds == ["planner"]
    assert any(getattr(route, "path", None) == "/a2a/planner" for route in host.routes)


def test_agent_post_process_mounts_on_existing_asgi_hosts() -> None:
    """Agent Pod가 처리될 때 이미 등록된 ASGI host에 app이 mount된다."""
    agent = ServedPlannerAgent(StubModel())
    registry = A2AAgentRegistry()
    registry.register(agent, ServedPlannerAgent, _planner_marker())
    spec = _ServerSpec()
    host = Starlette()

    processed = _processor(registry, spec, host).post_process(agent)

    assert processed is agent
    assert spec.builds == ["planner"]


def test_declared_rest_mount_path_mounts_rest_app() -> None:
    """rest_mount_path 선언이 있으면 REST app도 별도 path에 mount된다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(rest_mount_path="/a2a-rest/planner"),
    )
    spec = _ServerSpec(rest_mount_path="/a2a-rest/planner")
    host = Starlette()

    _processor(registry, spec).post_process(host)

    paths = {getattr(route, "path", None) for route in host.routes}
    assert "/a2a/planner" in paths
    assert "/a2a-rest/planner" in paths
    assert spec.builds == ["planner"]
    assert spec.rest_builds == ["planner"]


def test_rest_and_jsonrpc_cannot_claim_same_path() -> None:
    """REST와 JSON-RPC transport가 같은 path를 공유하면 route 충돌로 거부한다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(rest_mount_path="/a2a/planner"),
    )

    with pytest.raises(A2AEndpointConflictError):
        _processor(registry, _ServerSpec(rest_mount_path="/a2a/planner")).post_process(
            Starlette()
        )


def test_unmarked_agent_is_returned_without_mounting() -> None:
    """A2A marker가 없는 Agent Pod는 auto-mount 대상이 아니다."""
    registry = A2AAgentRegistry()
    spec = _ServerSpec()
    host = Starlette()

    processed = _processor(registry, spec, host).post_process(
        UnservedAgent(StubModel())
    )

    assert isinstance(processed, UnservedAgent)
    assert spec.builds == []


def test_dynamic_proxy_type_is_unwrapped_before_mounting() -> None:
    """AOP dynamic proxy subclass도 원본 Agent marker로 mount된다."""

    class ServedPlannerAgentDynamicProxy(ServedPlannerAgent):
        pass

    ServedPlannerAgentDynamicProxy.__name__ = (
        f"ServedPlannerAgent{DYNAMIC_PROXY_CLASS_NAME_SUFFIX}"
    )
    proxy = ServedPlannerAgentDynamicProxy(StubModel())
    registry = A2AAgentRegistry()
    registry.register(proxy, ServedPlannerAgent, _planner_marker())
    spec = _ServerSpec()
    host = Starlette()

    _processor(registry, spec, host).post_process(proxy)

    assert spec.builds == ["planner"]


def test_mounting_same_agent_twice_is_idempotent() -> None:
    """동일 agent의 post-process 반복은 route를 다시 추가하지 않는다."""
    agent = ServedPlannerAgent(StubModel())
    registry = A2AAgentRegistry()
    registry.register(agent, ServedPlannerAgent, _planner_marker())
    spec = _ServerSpec()
    host = Starlette()
    processor = _processor(registry, spec, host)

    processor.post_process(agent)
    processor.post_process(agent)

    assert spec.builds == ["planner"]


def test_path_conflict_between_agents_is_rejected() -> None:
    """서로 다른 A2A agent가 같은 mount path를 claim하면 실패한다."""

    from spakky.agent import Agent, AgentExecutionSpec
    from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

    @A2ACompatible()
    @Agent(spec=AgentExecutionSpec(name="writer", objective="write"))
    class WriterAgent:
        def __init__(self) -> None:
            self.ready = True

    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()), ServedPlannerAgent, _planner_marker()
    )
    registry.register(WriterAgent(), WriterAgent, A2ACompatible())

    with pytest.raises(A2AEndpointConflictError):
        _processor(registry, _ServerSpec()).post_process(Starlette())


def _planner_marker(rest_mount_path: str | None = None):
    from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

    return A2ACompatible(
        base_url="http://planner.local",
        version="1.2.3",
        rest_mount_path=rest_mount_path,
    )
