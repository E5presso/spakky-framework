"""Plugin initialization for the AG-UI SSE adapter.

Design decision — public hook over live auto-wiring:

``initialize`` registers only ``AgUiConfig``. It deliberately does **not** try to
resolve a FastAPI Pod and auto-mount the endpoint, for two reasons that make the
public hook the cleaner of the two options the spec allows:

1. The projector is stateful *per run* (it tracks the open message, reasoning,
   and tool frames), so it cannot be a shared singleton Pod — it must be
   constructed per request inside the driver. Registering it as a Pod would be
   misleading rather than useful.
2. ``add_agui_endpoint`` needs a ``run_driver_factory`` that resolves *which*
   declared ``@Agent`` answers a request and builds its ``AgentRunner``. That
   choice is application-specific; the plugin cannot guess it from the container
   without inventing an agent-selection convention the framework does not have.

So the application author calls ``add_agui_endpoint(app, run_driver_factory=...,
config=...)`` explicitly, resolving ``AgUiConfig`` from the container and binding
the factory to their agent. This mirrors pydantic-ai's
``add_*_fastapi_endpoint`` hook and keeps the plugin from importing the
``spakky-fastapi`` plugin (depending on third-party ``fastapi`` directly is
allowed; importing a sibling plugin's ``src`` is not — .agents/rules/plugin.md).
"""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.agui.config import AgUiConfig


def initialize(app: SpakkyApplication) -> None:
    """Register AG-UI configuration for the SSE adapter.

    Endpoint wiring is the application author's call via ``add_agui_endpoint``;
    see the module docstring for why auto-wiring is not attempted here.
    """
    app.add(AgUiConfig)
