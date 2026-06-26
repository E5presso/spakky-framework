"""Unit tests for declarative AG-UI FastAPI auto-mounting."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from json import loads
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from spakky.agent import Agent, AgentExecutionSpec, IAgentRunnerFactory
from spakky.agent.event import AgentEvent, AgentEventAttribution, RunFinishedEvent
from spakky.agent.runner import AgentRunner
from spakky.core.common.constants import DYNAMIC_PROXY_CLASS_NAME_SUFFIX
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.core.pod.interfaces.container import IContainer

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.error import AgUiEndpointConflictError, AgUiRunResolutionError
from spakky.plugins.agui.post_processors.mount_fastapi import (
    MountAgUiFastAPIPostProcessor,
)
from spakky.plugins.agui.server.registry import AgUiAgentRegistry
from spakky.plugins.agui.stereotypes.agui_compatible import AGUICompatible


@AGUICompatible()
@Agent(spec=AgentExecutionSpec(name="assistant", objective="answer"))
class _MountedAssistant:
    """Agent fixture exposed through the AG-UI auto-mount path."""


@AGUICompatible()
@Agent(spec=AgentExecutionSpec(name="researcher", objective="research"))
class _MountedResearcher:
    """Second fixture used to prove path conflict detection."""


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
    def __init__(self, values: dict[type[object], object]) -> None:
        self._values = values

    def get(self, type_: type[object]) -> object:
        return self._values[type_]


class _Runner:
    signals = None

    async def run_events(self, run_input: object) -> AsyncIterator[AgentEvent]:
        yield RunFinishedEvent(
            attribution=AgentEventAttribution(
                agent_id="assistant",
                run_id="run-1",
                conversation_id="conv-1",
            )
        )


class _RunnerFactory:
    def open_runner(
        self,
        agent_instance: object,
        server_names: object = None,
    ) -> "_RunnerContext":
        return _RunnerContext()


class _RunnerContext:
    async def __aenter__(self) -> AgentRunner:
        return cast(AgentRunner, _Runner())

    async def __aexit__(self, *_: object) -> None:
        return None


def _run_input() -> dict[str, object]:
    return {
        "threadId": "conv-1",
        "runId": "run-1",
        "state": None,
        "messages": [{"id": "u1", "role": "user", "content": "hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }


def _processor(
    registry: AgUiAgentRegistry,
    app: FastAPI | None = None,
) -> MountAgUiFastAPIPostProcessor:
    processor = MountAgUiFastAPIPostProcessor()
    processor.set_container(
        cast(
            IContainer,
            _Container(
                {
                    AgUiConfig: AgUiConfig(),
                    AgUiAgentRegistry: registry,
                    IAgentRunnerFactory: _RunnerFactory(),
                }
            ),
        )
    )
    pods: tuple[tuple[object, _PodRecord], ...] = ()
    if app is not None:
        pods = ((app, _PodRecord(type_=FastAPI, base_types=())),)
    processor.set_application_context(
        cast(IApplicationContext, _ApplicationContext(pods))
    )
    return processor


def test_app_post_process_mounts_registered_agent_routes() -> None:
    """FastAPI Pod가 나중에 처리되어도 registry의 AG-UI agent routes가 붙는다."""
    registry = AgUiAgentRegistry()
    registry.register(
        _MountedAssistant(), _MountedAssistant, AGUICompatible.get(_MountedAssistant)
    )
    app = FastAPI()

    processed = _processor(registry).post_process(app)

    assert processed is app
    response = TestClient(app).post("/agui", json=_run_input())
    assert response.status_code == 200
    event_types = [
        loads(frame.removeprefix("data: ").strip())["type"]
        for frame in response.text.split("\n\n")
        if frame.startswith("data: ")
    ]
    assert event_types == ["RUN_FINISHED"]


def test_agent_post_process_mounts_on_existing_fastapi_hosts() -> None:
    """Agent Pod가 나중에 처리되어도 이미 등록된 FastAPI host에 route가 붙는다."""
    registry = AgUiAgentRegistry()
    app = FastAPI()
    agent = _MountedAssistant()

    processed = _processor(registry, app).post_process(agent)

    assert processed is agent
    assert registry.get("assistant").instance is agent
    assert TestClient(app).post("/agui", json=_run_input()).status_code == 200


def test_mounting_same_agent_twice_is_idempotent() -> None:
    """동일 agent의 중복 post-process는 같은 route를 다시 추가하지 않는다."""
    registry = AgUiAgentRegistry()
    app = FastAPI()
    agent = _MountedAssistant()
    processor = _processor(registry, app)

    processor.post_process(agent)
    route_count = len(app.routes)
    processor.post_process(agent)

    assert len(app.routes) == route_count


def test_dynamic_proxy_type_is_unwrapped_before_mounting() -> None:
    """AOP dynamic proxy subclass도 원본 @AGUICompatible marker로 등록된다."""

    class MountedAssistantDynamicProxy(_MountedAssistant):
        marker = "proxy"

    MountedAssistantDynamicProxy.__name__ = (
        f"MountedAssistant{DYNAMIC_PROXY_CLASS_NAME_SUFFIX}"
    )
    registry = AgUiAgentRegistry()
    app = FastAPI()
    proxy = MountedAssistantDynamicProxy()

    _processor(registry, app).post_process(proxy)

    entry = registry.get("assistant")
    assert entry.instance is proxy
    assert entry.agent_type is _MountedAssistant


def test_auto_mount_detects_path_conflicts_between_agents() -> None:
    """서로 다른 AG-UI agent가 같은 path를 claim하면 conflict로 실패한다."""
    registry = AgUiAgentRegistry()
    registry.register(
        _MountedAssistant(), _MountedAssistant, AGUICompatible.get(_MountedAssistant)
    )
    registry.register(
        _MountedResearcher(), _MountedResearcher, AGUICompatible.get(_MountedResearcher)
    )

    try:
        _processor(registry).post_process(FastAPI())
    except AgUiEndpointConflictError:
        return

    raise AssertionError("expected AG-UI path conflict")


def test_registry_get_unknown_agent_raises_resolution_error() -> None:
    """registry는 등록되지 않은 agent 이름을 resolution error로 거부한다."""
    try:
        AgUiAgentRegistry().get("missing")
    except AgUiRunResolutionError:
        return

    raise AssertionError("expected missing AG-UI agent lookup to fail")


def test_registry_lists_entries_by_agent_name() -> None:
    """registry list는 agent 이름 기준 stable order를 보존한다."""
    registry = AgUiAgentRegistry()
    registry.register(
        _MountedResearcher(), _MountedResearcher, AGUICompatible.get(_MountedResearcher)
    )
    registry.register(
        _MountedAssistant(), _MountedAssistant, AGUICompatible.get(_MountedAssistant)
    )

    assert [entry.agent_name for entry in registry.list_entries()] == [
        "assistant",
        "researcher",
    ]
