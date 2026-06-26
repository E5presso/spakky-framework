"""Tests for spakky-agui public API exports."""

import spakky.plugins.agui as agui_api
from spakky.plugins.agui import (
    AbstractAgUiError,
    AGUICompatible,
    AgUiAgent,
    AgUiAgentEntry,
    AgUiAgentRegistry,
    AgUiApprovalDecodeError,
    AgUiConfig,
    AgUiEndpointConflictError,
    AgUiManagedRunDriver,
    AgUiPendingApprovalError,
    AgUiProjector,
    AgUiRunDriver,
    AgUiRunResolutionError,
    AgUiStdioCommand,
    PLUGIN_NAME,
    RunDriverFactory,
    add_agui_endpoint,
    add_agui_http_stream_endpoint,
    add_agui_websocket_endpoint,
    agui_stdio_payloads,
    approval_from_pause,
    ingest_decision,
    project_approval,
    project_pending_approval,
    read_agui_run_input,
    run_agui_stdio,
)


def test_public_api_exports_agui_surface() -> None:
    """public API가 plugin id, config, adapter 구성요소, 에러, hook을 노출한다."""
    assert PLUGIN_NAME.name == "spakky-agui"
    assert AgUiConfig is agui_api.AgUiConfig
    assert AGUICompatible is agui_api.AGUICompatible
    assert AgUiAgent is AGUICompatible
    assert AgUiAgentEntry is agui_api.AgUiAgentEntry
    assert AgUiAgentRegistry is agui_api.AgUiAgentRegistry
    assert AgUiProjector is agui_api.AgUiProjector
    assert AgUiManagedRunDriver is agui_api.AgUiManagedRunDriver
    assert AgUiRunDriver is agui_api.AgUiRunDriver
    assert AgUiStdioCommand is agui_api.AgUiStdioCommand
    assert add_agui_endpoint is agui_api.add_agui_endpoint
    assert add_agui_http_stream_endpoint is agui_api.add_agui_http_stream_endpoint
    assert add_agui_websocket_endpoint is agui_api.add_agui_websocket_endpoint
    assert agui_stdio_payloads is agui_api.agui_stdio_payloads
    assert approval_from_pause is agui_api.approval_from_pause
    assert ingest_decision is agui_api.ingest_decision
    assert project_approval is agui_api.project_approval
    assert project_pending_approval is agui_api.project_pending_approval
    assert read_agui_run_input is agui_api.read_agui_run_input
    assert run_agui_stdio is agui_api.run_agui_stdio
    assert RunDriverFactory is agui_api.RunDriverFactory
    assert AbstractAgUiError is agui_api.AbstractAgUiError
    assert AgUiApprovalDecodeError is agui_api.AgUiApprovalDecodeError
    assert AgUiEndpointConflictError is agui_api.AgUiEndpointConflictError
    assert AgUiPendingApprovalError is agui_api.AgUiPendingApprovalError
    assert AgUiRunResolutionError is agui_api.AgUiRunResolutionError
