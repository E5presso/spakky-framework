"""Tests for A2A app assembly and the container-aware server spec."""

from unittest.mock import MagicMock

import pytest
from spakky.core.pod.interfaces.container import IContainer
from starlette.applications import Starlette

from spakky.plugins.a2a.error import A2AAgentServerNotRegisteredError
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
    registry.register(ServedPlannerAgent(StubModel()), _planner_marker())
    repository = InMemoryA2ATaskRepository()
    container = MagicMock(spec=IContainer)
    container.get = MagicMock(return_value=registry)
    container.get_or_none = MagicMock(return_value=repository)

    app = _spec_with_container(container).build_app_for("planner")

    assert isinstance(app, Starlette)
    container.get_or_none.assert_called_once_with(IA2ATaskRepository)


def _planner_marker():
    from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer

    return A2AAgentServer(base_url="http://planner.local", version="1.2.3")
