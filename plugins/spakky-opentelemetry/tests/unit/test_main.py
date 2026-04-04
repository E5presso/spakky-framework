"""Tests for plugin initialization."""

from unittest.mock import MagicMock, call

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.opentelemetry.bridge import LogContextBridge
from spakky.plugins.opentelemetry.config import OpenTelemetryConfig
from spakky.plugins.opentelemetry.main import initialize
from spakky.plugins.opentelemetry.post_processor import OTelSetupPostProcessor


def test_initialize_registers_all_pods() -> None:
    """initialize()가 Config, PostProcessor, LogContextBridge를 등록한다."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_has_calls(
        [
            call(OpenTelemetryConfig),
            call(OTelSetupPostProcessor),
            call(LogContextBridge),
        ],
    )
    assert app.add.call_count == 3
