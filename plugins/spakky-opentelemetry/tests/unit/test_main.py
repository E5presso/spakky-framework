"""Tests for plugin initialization."""

from unittest.mock import MagicMock, call

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.opentelemetry.config import OpenTelemetryConfig
from spakky.plugins.opentelemetry.main import initialize
from spakky.plugins.opentelemetry.post_processor import OTelSetupPostProcessor


def test_initialize_registers_config_and_post_processor() -> None:
    """initialize()가 OpenTelemetryConfig과 OTelSetupPostProcessor를 등록한다."""
    app = MagicMock(spec=SpakkyApplication)

    initialize(app)

    app.add.assert_has_calls(
        [call(OpenTelemetryConfig), call(OTelSetupPostProcessor)],
    )
    assert app.add.call_count == 2
