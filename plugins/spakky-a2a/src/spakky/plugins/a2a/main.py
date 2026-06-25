"""Plugin initialization for the A2A protocol server integration.

Registers the plugin configuration, the agent-server registry, the container-aware
app-builder spec, and the post-processor that discovers @A2AAgentServer-marked
@Agent Pods. This function is called automatically during plugin loading.
"""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.a2a.config import A2AConfig
from spakky.plugins.a2a.post_processors.register_agent_servers import (
    RegisterA2AAgentServersPostProcessor,
)
from spakky.plugins.a2a.server.builder import A2AAgentServerSpec
from spakky.plugins.a2a.server.registry import A2AAgentRegistry


def initialize(app: SpakkyApplication) -> None:
    """Initialize the A2A plugin.

    Args:
        app: The Spakky application instance.
    """
    app.add(A2AConfig)
    app.add(A2AAgentRegistry)
    app.add(A2AAgentServerSpec)
    app.add(RegisterA2AAgentServersPostProcessor)
