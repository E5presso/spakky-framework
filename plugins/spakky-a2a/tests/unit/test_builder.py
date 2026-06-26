"""Tests for A2A app assembly and the container-aware server spec."""

from unittest.mock import MagicMock

import pytest
from spakky.core.pod.interfaces.container import IContainer
from starlette.applications import Starlette

from spakky.plugins.a2a.error import A2AAgentServerNotRegisteredError
from spakky.plugins.a2a.config import A2AConfig
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec, build_a2a_app
from spakky.plugins.a2a.server.registry import A2AAgentRegistry
from spakky.plugins.a2a.store.interfaces import IA2ATaskRepository
from spakky.plugins.a2a.store.task_store import InMemoryA2ATaskRepository
from tests.unit._sample_agents import ServedPlannerAgent, StubModel


def test_build_a2a_app_assembles_a_starlette_app() -> None:
    """build_a2a_app returns a Starlette app carrying card and rpc routes."""
    app = build_a2a_app(
        ServedPlannerAgent(StubModel()),
        base_url="http://x",
        version="1.0.0",
    )

    assert isinstance(app, Starlette)
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/.well-known/agent-card.json" in paths


def test_build_a2a_app_uses_default_in_memory_store_when_none() -> None:
    """An omitted repository still yields a working app (in-memory store)."""
    app = build_a2a_app(
        ServedPlannerAgent(StubModel()),
        base_url="http://x",
        version="1.0.0",
        repository=None,
    )

    assert isinstance(app, Starlette)


def _spec_with_container(container: IContainer) -> A2AAgentServerSpec:
    spec = A2AAgentServerSpec()
    spec.set_container(container)
    return spec


def test_server_spec_builds_app_for_registered_agent() -> None:
    """The spec resolves a registered agent and builds its app."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(),
    )
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    container.get_or_none = MagicMock(return_value=None)

    app = _spec_with_container(container).build_app_for("planner")

    assert isinstance(app, Starlette)


def test_server_spec_unknown_agent_raises() -> None:
    """Building an app for an unregistered agent raises the registry error."""
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=A2AAgentRegistry())
    container.get_or_none = MagicMock(return_value=None)

    with pytest.raises(A2AAgentServerNotRegisteredError):
        _spec_with_container(container).build_app_for("absent")


def test_server_spec_uses_container_repository_when_present() -> None:
    """A repository Pod resolved from the container is passed to the builder."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()), ServedPlannerAgent, _planner_marker()
    )
    repository = InMemoryA2ATaskRepository()
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    container.get_or_none = MagicMock(return_value=repository)

    app = _spec_with_container(container).build_app_for("planner")

    assert isinstance(app, Starlette)
    container.get_or_none.assert_called_once_with(IA2ATaskRepository)


def test_server_spec_builds_rest_app_for_registered_agent() -> None:
    """The spec can build the declared REST transport from the registry."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(rest_mount_path="/rest/planner"),
    )
    config = A2AConfig()
    config.default_base_url = "https://agents.example.com"
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(
        side_effect=lambda key: config if key is A2AConfig else registry
    )
    container.get_or_none = MagicMock(return_value=None)

    app = _spec_with_container(container).build_rest_app_for("planner")

    assert isinstance(app, Starlette)


def test_server_spec_builds_grpc_handler_for_registered_agent() -> None:
    """The spec can build the declared gRPC handler from the registry."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(grpc_base_url="grpc://planner.local"),
    )
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    container.get_or_none = MagicMock(return_value=None)

    handler = _spec_with_container(container).build_grpc_handler_for("planner")

    assert handler is not None


def test_server_spec_mount_path_uses_marker_override() -> None:
    """@A2ACompatible mount_path가 있으면 config prefix 대신 그 값을 쓴다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(mount_path="/custom/planner"),
    )
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)

    assert (
        _spec_with_container(container).mount_path_for("planner") == "/custom/planner"
    )


def test_server_spec_derives_default_base_url_from_mount_path() -> None:
    """base_url 생략 시 default_base_url과 실제 mount path를 합쳐 광고한다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(base_url=None, mount_path="/custom/planner"),
    )
    config = A2AConfig()
    config.default_base_url = "https://agents.example.com/root/"
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(
        side_effect=lambda key: config if key is A2AConfig else registry
    )

    entry = registry.get("planner")

    assert (
        _spec_with_container(container)._base_url(entry)
        == "https://agents.example.com/root/custom/planner"
    )


def test_server_spec_rest_base_url_uses_explicit_value() -> None:
    """rest_base_url이 있으면 REST mount path에서 유도하지 않는다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(
            base_url=None,
            rest_mount_path="/rest/planner",
            rest_base_url="https://rest.example/planner",
        ),
    )
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    entry = registry.get("planner")

    assert (
        _spec_with_container(container)._rest_base_url(entry)
        == "https://rest.example/planner"
    )


def test_server_spec_rest_base_url_falls_back_to_agent_base_url() -> None:
    """REST 전용 endpoint가 없으면 AgentCard base_url을 재사용한다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(base_url="https://agents.example.com/a2a/planner"),
    )
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    entry = registry.get("planner")

    assert (
        _spec_with_container(container)._rest_base_url(entry)
        == "https://agents.example.com/a2a/planner"
    )


def test_server_spec_grpc_base_url_falls_back_to_agent_base_url() -> None:
    """grpc_base_url을 생략하면 AgentCard base_url을 재사용한다."""
    registry = A2AAgentRegistry()
    registry.register(
        ServedPlannerAgent(StubModel()),
        ServedPlannerAgent,
        _planner_marker(base_url="https://agents.example.com/a2a/planner"),
    )
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    entry = registry.get("planner")

    assert (
        _spec_with_container(container)._grpc_base_url(entry)
        == "https://agents.example.com/a2a/planner"
    )


def _planner_marker(
    base_url: str | None = "http://planner.local",
    mount_path: str | None = None,
    rest_mount_path: str | None = None,
    rest_base_url: str | None = None,
    grpc_base_url: str | None = None,
):
    from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

    return A2ACompatible(
        base_url=base_url,
        version="1.2.3",
        mount_path=mount_path,
        rest_mount_path=rest_mount_path,
        rest_base_url=rest_base_url,
        grpc_base_url=grpc_base_url,
    )
