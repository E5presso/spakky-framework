"""Tests for OTelSetupPostProcessor."""

from unittest.mock import MagicMock

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from spakky.core.pod.interfaces.container import IContainer
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.opentelemetry.config import ExporterType, OpenTelemetryConfig
from spakky.plugins.opentelemetry.post_processor import OTelSetupPostProcessor
from spakky.plugins.opentelemetry.propagator import OTelTracePropagator


def _make_config(
    exporter_type: ExporterType = ExporterType.NONE,
) -> OpenTelemetryConfig:
    """테스트용 OpenTelemetryConfig을 생성한다."""
    config = OpenTelemetryConfig.__new__(OpenTelemetryConfig)
    object.__setattr__(config, "service_name", "test-service")
    object.__setattr__(config, "exporter_type", exporter_type)
    object.__setattr__(config, "exporter_endpoint", "http://localhost:4317")
    object.__setattr__(config, "sample_rate", 1.0)
    return config


def _make_processor(
    exporter_type: ExporterType = ExporterType.NONE,
) -> OTelSetupPostProcessor:
    """테스트용 post-processor를 생성한다."""
    container = MagicMock(spec=IContainer)
    container.get.return_value = _make_config(exporter_type)

    processor = OTelSetupPostProcessor()
    processor.set_container(container)
    return processor


def test_replace_w3c_propagator_expect_otel_propagator() -> None:
    """W3CTracePropagator Pod를 OTelTracePropagator로 교체한다."""
    processor = _make_processor()
    w3c = W3CTracePropagator()

    result = processor.post_process(w3c)

    assert isinstance(result, OTelTracePropagator)


def test_passthrough_other_pod_expect_unchanged() -> None:
    """W3CTracePropagator가 아닌 Pod는 그대로 반환한다."""
    processor = _make_processor()
    other = object()

    result = processor.post_process(other)

    assert result is other


def test_configure_tracer_provider_with_none_exporter() -> None:
    """ExporterType.NONE이면 TracerProvider를 exporter 없이 설정한다."""
    processor = _make_processor(ExporterType.NONE)

    processor.post_process(object())

    provider = trace.get_tracer_provider()
    assert provider is not None


def test_configure_tracer_provider_with_console_exporter() -> None:
    """ExporterType.CONSOLE이면 ConsoleSpanExporter로 TracerProvider를 설정한다."""
    processor = _make_processor(ExporterType.CONSOLE)

    processor.post_process(object())

    provider = trace.get_tracer_provider()
    assert provider is not None


def test_configure_tracer_provider_with_otlp_exporter() -> None:
    """ExporterType.OTLP이면 OTLPSpanExporter로 TracerProvider를 설정한다."""
    processor = _make_processor(ExporterType.OTLP)

    processor.post_process(object())

    provider = trace.get_tracer_provider()
    assert provider is not None


def test_configure_once_expect_idempotent() -> None:
    """post_process를 여러 번 호출해도 TracerProvider는 한 번만 설정한다."""
    processor = _make_processor()

    processor.post_process(object())
    processor.post_process(object())

    # No exception = idempotent configuration


def test_first_pod_is_w3c_expect_replaced_and_configured() -> None:
    """첫 번째 Pod가 W3CTracePropagator면 교체와 설정 모두 수행한다."""
    processor = _make_processor()

    w3c = W3CTracePropagator()
    result = processor.post_process(w3c)

    assert isinstance(result, OTelTracePropagator)


def test_create_exporter_console_expect_console_exporter() -> None:
    """_create_exporter에 CONSOLE을 전달하면 ConsoleSpanExporter를 반환한다."""
    config = _make_config(ExporterType.CONSOLE)

    result = OTelSetupPostProcessor._create_exporter(config)

    assert isinstance(result, ConsoleSpanExporter)


def test_create_exporter_otlp_expect_otlp_exporter() -> None:
    """_create_exporter에 OTLP를 전달하면 OTLPSpanExporter를 반환한다."""
    config = _make_config(ExporterType.OTLP)

    result = OTelSetupPostProcessor._create_exporter(config)

    assert isinstance(result, OTLPSpanExporter)


def test_create_exporter_none_expect_none() -> None:
    """_create_exporter에 NONE을 전달하면 None을 반환한다."""
    config = _make_config(ExporterType.NONE)

    result = OTelSetupPostProcessor._create_exporter(config)

    assert result is None
