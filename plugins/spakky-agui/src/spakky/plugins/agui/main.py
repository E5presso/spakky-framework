"""Plugin initialization for the AG-UI adapter."""

from spakky.core.application.application import SpakkyApplication
from spakky.agent import AgentRunnerFactory, IAgentRunnerFactory

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.post_processors.mount_fastapi import (
    MountAgUiFastAPIPostProcessor,
)
from spakky.plugins.agui.server.registry import AgUiAgentRegistry


def initialize(app: SpakkyApplication) -> None:
    """Register AG-UI configuration, registry, and auto-mount post-processor."""
    if not app.container.contains(IAgentRunnerFactory):
        app.add(AgentRunnerFactory)
    app.add(AgUiConfig)
    app.add(AgUiAgentRegistry)
    app.add(MountAgUiFastAPIPostProcessor)
