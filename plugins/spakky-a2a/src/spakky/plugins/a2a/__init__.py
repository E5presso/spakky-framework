"""A2A (Agent2Agent) protocol server plugin for the Spakky framework.

Exposes a spakky ``@Agent`` as an A2A protocol server: an AgentCard is derived
from the agent's spec, tools, and teammates, and JSON-RPC/HTTP plus SSE routes
are mounted from the official ``a2a-sdk``. Marker, config, and plugin identifier
are re-exported; transport types live under ``a2a-sdk``.
"""

from spakky.core.application.plugin import Plugin

from spakky.plugins.a2a.config import (
    SPAKKY_A2A_CONFIG_ENV_PREFIX,
    A2AConfig,
)
from spakky.plugins.a2a.client import A2ARemoteAgentClient, RemoteA2AMessage
from spakky.plugins.a2a.delegation import A2AAgentDelegate, A2AStreamEventMapper
from spakky.plugins.a2a.error import A2AEndpointConflictError
from spakky.plugins.a2a.stereotypes.a2a_agent_server import A2AAgentServer
from spakky.plugins.a2a.stereotypes.a2a_compatible import A2ACompatible

PLUGIN_NAME = Plugin(name="spakky-a2a")
"""Plugin identifier for the A2A integration."""

__all__ = [
    "PLUGIN_NAME",
    "SPAKKY_A2A_CONFIG_ENV_PREFIX",
    "A2AConfig",
    "A2AAgentDelegate",
    "A2ARemoteAgentClient",
    "A2AStreamEventMapper",
    "A2ACompatible",
    "A2AAgentServer",
    "A2AEndpointConflictError",
    "RemoteA2AMessage",
]
