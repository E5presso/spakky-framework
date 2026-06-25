"""Tests for spakky-agui public API exports."""

import spakky.plugins.agui as agui_api
from spakky.plugins.agui import (
    AbstractAgUiError,
    AgUiApprovalDecodeError,
    AgUiConfig,
    AgUiPendingApprovalError,
    AgUiProjector,
    AgUiRunDriver,
    AgUiRunResolutionError,
    PLUGIN_NAME,
    RunDriverFactory,
    add_agui_endpoint,
    add_agui_http_stream_endpoint,
    add_agui_websocket_endpoint,
    ingest_decision,
    project_approval,
    project_pending_approval,
)


def test_public_api_exports_agui_surface() -> None:
    """public API가 plugin id, config, adapter 구성요소, 에러, hook을 노출한다."""
    assert PLUGIN_NAME.name == "spakky-agui"
    assert AgUiConfig is agui_api.AgUiConfig
    assert AgUiProjector is agui_api.AgUiProjector
    assert AgUiRunDriver is agui_api.AgUiRunDriver
    assert add_agui_endpoint is agui_api.add_agui_endpoint
    assert add_agui_http_stream_endpoint is agui_api.add_agui_http_stream_endpoint
    assert add_agui_websocket_endpoint is agui_api.add_agui_websocket_endpoint
    assert ingest_decision is agui_api.ingest_decision
    assert project_approval is agui_api.project_approval
    assert project_pending_approval is agui_api.project_pending_approval
    assert RunDriverFactory is agui_api.RunDriverFactory
    assert AbstractAgUiError is agui_api.AbstractAgUiError
    assert AgUiApprovalDecodeError is agui_api.AgUiApprovalDecodeError
    assert AgUiPendingApprovalError is agui_api.AgUiPendingApprovalError
    assert AgUiRunResolutionError is agui_api.AgUiRunResolutionError
