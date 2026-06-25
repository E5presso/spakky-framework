"""AG-UI protocol adapter plugin for Spakky Agent."""

from spakky.core.application.plugin import Plugin

from spakky.plugins.agui.config import AgUiConfig
from spakky.plugins.agui.endpoint import RunDriverFactory, add_agui_endpoint
from spakky.plugins.agui.error import (
    AbstractAgUiError,
    AgUiApprovalDecodeError,
    AgUiPendingApprovalError,
    AgUiRunResolutionError,
)
from spakky.plugins.agui.hitl import (
    ingest_decision,
    project_approval,
    project_pending_approval,
)
from spakky.plugins.agui.projector import AgUiProjector
from spakky.plugins.agui.transport import AgUiRunDriver

PLUGIN_NAME = Plugin(name="spakky-agui")
"""Plugin identifier for the AG-UI adapter package."""

__all__ = [
    "AbstractAgUiError",
    "AgUiApprovalDecodeError",
    "AgUiConfig",
    "AgUiPendingApprovalError",
    "AgUiProjector",
    "AgUiRunDriver",
    "AgUiRunResolutionError",
    "PLUGIN_NAME",
    "RunDriverFactory",
    "add_agui_endpoint",
    "ingest_decision",
    "project_approval",
    "project_pending_approval",
]
