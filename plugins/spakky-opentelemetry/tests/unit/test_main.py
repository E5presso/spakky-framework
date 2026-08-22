"""Tests for plugin initialization."""

from unittest.mock import MagicMock, call

from spakky.agent.telemetry import IAgentTelemetry
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.opentelemetry.bridge import LogContextBridge
from spakky.plugins.opentelemetry.config import OpenTelemetryConfig
from spakky.plugins.opentelemetry.main import initialize
from spakky.plugins.opentelemetry.post_processor import OTelSetupPostProcessor
from spakky.plugins.opentelemetry.telemetry import OpenTelemetryAgentTelemetry


def test_initialize_registers_all_pods() -> None:
    """initialize()가 기존 bridge와 Agent telemetry binding을 함께 등록한다."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_has_calls(
        [
            call(OpenTelemetryConfig),
            call(OTelSetupPostProcessor),
            call(LogContextBridge),
            call(OpenTelemetryAgentTelemetry),
        ],
    )
    assert app.add.call_count == 4
    app.container.bind_to_type.assert_called_once_with(
        IAgentTelemetry,
        OpenTelemetryAgentTelemetry,
    )
