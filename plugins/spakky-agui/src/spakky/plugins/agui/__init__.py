"""AG-UI protocol adapter plugin for Spakky Agent."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import RunDriverFactory, add_agui_endpoint
from spakky.plugins.agui.error import (
    AbstractAgUiError,
    AgUiApprovalDecodeError,
    AgUiEndpointConflictError,
    AgUiPendingApprovalError,
    AgUiRunResolutionError,
)
from spakky.plugins.agui.hitl import (
    approval_from_pause,
    ingest_decision,
    project_approval,
    project_pending_approval,
)
from spakky.plugins.agui.http_stream import add_agui_http_stream_endpoint
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.server.registry import AgUiAgentEntry, AgUiAgentRegistry
from spakky.plugins.agui.stdio import (
    AgUiStdioCommand,
    agui_stdio_payloads,
    read_agui_run_input,
    run_agui_stdio,
)
from spakky.plugins.agui.stereotypes.agui_agent import AgUiAgent
from spakky.plugins.agui.stereotypes.agui_compatible import AGUICompatible
from spakky.plugins.agui.transport import AgUiManagedRunDriver, AgUiRunDriver
from spakky.plugins.agui.websocket import add_agui_websocket_endpoint

PLUGIN_NAME = Plugin(name="spakky-agui")
"""Plugin identifier for the AG-UI adapter package."""

__all__ = [
    "AbstractAgUiError",
    "AgUiApprovalDecodeError",
    "AgUiConfig",
    "AgUiEndpointConflictError",
    "AGUICompatible",
    "AgUiAgent",
    "AgUiAgentEntry",
    "AgUiAgentRegistry",
    "AgUiPendingApprovalError",
    "AgUiProjector",
    "AgUiManagedRunDriver",
    "AgUiRunDriver",
    "AgUiStdioCommand",
    "AgUiRunResolutionError",
    "PLUGIN_NAME",
    "RunDriverFactory",
    "add_agui_endpoint",
    "add_agui_http_stream_endpoint",
    "add_agui_websocket_endpoint",
    "agui_stdio_payloads",
    "approval_from_pause",
    "ingest_decision",
    "project_approval",
    "project_pending_approval",
    "read_agui_run_input",
    "run_agui_stdio",
]
