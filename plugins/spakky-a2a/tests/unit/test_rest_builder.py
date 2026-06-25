"""Tests for A2A REST app assembly."""

from starlette.applications import Starlette
from starlette.routing import Route

from spakky.plugins.a2a.rest_transport.builder import build_a2a_rest_app
from tests.unit._sample_agents import ServedPlannerAgent, StubModel


def test_build_a2a_rest_app_assembles_http_json_routes() -> None:
    """build_a2a_rest_app returns a Starlette app with REST operation routes."""
    app = build_a2a_rest_app(
        ServedPlannerAgent(StubModel()),
        base_url="http://x",
        version="1.0.0",
    )

    assert isinstance(app, Starlette)
    paths = {route.path for route in app.routes if isinstance(route, Route)}
    assert "/.well-known/agent-card.json" in paths
    assert "/message:send" in paths
    assert "/message:stream" in paths
    assert "/tasks/{id}" in paths
    assert "/tasks/{id}:cancel" in paths
    assert "/tasks/{id}:subscribe" in paths


def test_build_a2a_rest_app_respects_path_prefix() -> None:
    """REST operation routes can be mounted under an SDK path prefix."""
    app = build_a2a_rest_app(
        ServedPlannerAgent(StubModel()),
        base_url="http://x/a2a",
        version="1.0.0",
        path_prefix="/a2a",
    )

    paths = {route.path for route in app.routes if isinstance(route, Route)}
    assert "/a2a/message:send" in paths
    assert "/a2a/tasks/{id}" in paths
