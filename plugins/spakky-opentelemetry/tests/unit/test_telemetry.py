"""Tests for the Agent telemetry OpenTelemetry bridge."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind, StatusCode
from spakky.agent.error import AgentDefinitionError
from spakky.agent.telemetry import (
    AgentSpanKind,
    AgentSpanRecord,
    AgentSpanStatus,
)
from spakky.tracing.context import TraceContext

from spakky.plugins.opentelemetry.telemetry import OpenTelemetryAgentTelemetry


@pytest.fixture
def telemetry_exporter() -> Iterator[
    tuple[OpenTelemetryAgentTelemetry, InMemorySpanExporter, TracerProvider]
]:
    """Provide an isolated in-memory SDK pipeline without a global exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = OpenTelemetryAgentTelemetry(provider.get_tracer("test-agent"))
    try:
        yield telemetry, exporter, provider
    finally:
        TraceContext.clear()
        provider.shutdown()


def _finished_span(exporter: InMemorySpanExporter) -> ReadableSpan:
    """Return the single finished test span."""
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    return spans[0]


def test_record_with_trace_context_expect_exact_parent_time_and_attributes(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """Agent record fields become one exactly timed child OTel span."""
    telemetry, exporter, _provider = telemetry_exporter
    parent = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        trace_flags=1,
    )
    TraceContext.set(parent)
    record = AgentSpanRecord(
        name="agent.model",
        kind=AgentSpanKind.MODEL,
        started_at_ns=1_700_000_000_000_000_000,
        ended_at_ns=1_700_000_000_250_000_000,
        attributes={
            "agent.name": "planner",
            "attempt": 2,
            "cached": False,
            "score": 0.5,
        },
    )

    telemetry.record(record)

    exported = _finished_span(exporter)
    assert exported.name == "agent.model"
    assert exported.context is not None
    assert exported.context.trace_id == int(parent.trace_id, 16)
    assert exported.parent is not None
    assert exported.parent.span_id == int(parent.span_id, 16)
    assert exported.start_time == record.started_at_ns
    assert exported.end_time == record.ended_at_ns
    assert exported.attributes is not None
    assert exported.attributes["agent.name"] == "planner"
    assert exported.attributes["attempt"] == 2
    assert exported.attributes["cached"] is False
    assert exported.attributes["score"] == 0.5
    assert exported.attributes["gen_ai.operation.name"] == "generate_content"


@pytest.mark.parametrize(
    ("agent_kind", "operation_name", "otel_kind"),
    (
        (AgentSpanKind.RUN, "invoke_agent", SpanKind.INTERNAL),
        (AgentSpanKind.MODEL, "generate_content", SpanKind.CLIENT),
        (AgentSpanKind.TOOL, "execute_tool", SpanKind.INTERNAL),
        (AgentSpanKind.RETRIEVAL, "retrieval", SpanKind.CLIENT),
    ),
)
def test_record_agent_kind_expect_gen_ai_operation_and_span_kind(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
    agent_kind: AgentSpanKind,
    operation_name: str,
    otel_kind: SpanKind,
) -> None:
    """Each Agent operation family has a stable GenAI operation and OTel kind."""
    telemetry, exporter, _provider = telemetry_exporter

    telemetry.record(
        AgentSpanRecord(
            name=f"agent.{agent_kind.value}",
            kind=agent_kind,
            started_at_ns=10,
            ended_at_ns=20,
        )
    )

    exported = _finished_span(exporter)
    assert exported.kind is otel_kind
    assert exported.attributes is not None
    assert exported.attributes["gen_ai.operation.name"] == operation_name


def test_record_error_expect_error_status_and_code_attribute(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """Failed Agent records map their code to OTel status and error.type."""
    telemetry, exporter, _provider = telemetry_exporter

    telemetry.record(
        AgentSpanRecord(
            name="agent.tool",
            kind=AgentSpanKind.TOOL,
            started_at_ns=10,
            ended_at_ns=20,
            status=AgentSpanStatus.ERROR,
            error_code="tool_dispatch_failed",
        )
    )

    exported = _finished_span(exporter)
    assert exported.status.status_code is StatusCode.ERROR
    assert exported.status.description == "tool_dispatch_failed"
    assert exported.attributes is not None
    assert exported.attributes["error.type"] == "tool_dispatch_failed"


def test_record_success_expect_ok_status_without_error_attribute(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """Successful Agent records set OK without synthesizing an error code."""
    telemetry, exporter, _provider = telemetry_exporter

    telemetry.record(
        AgentSpanRecord(
            name="agent.run",
            kind=AgentSpanKind.RUN,
            started_at_ns=10,
            ended_at_ns=20,
        )
    )

    exported = _finished_span(exporter)
    assert exported.status.status_code is StatusCode.OK
    assert exported.attributes is not None
    assert "error.type" not in exported.attributes


def test_record_raw_body_attributes_expect_privacy_keys_omitted(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """Prompt, context, and tool body keys never reach the OTel exporter."""
    telemetry, exporter, _provider = telemetry_exporter
    raw_keys = OpenTelemetryAgentTelemetry._RAW_BODY_ATTRIBUTE_KEYS
    attributes: dict[str, str | int] = {key: "raw-secret-body" for key in raw_keys}
    attributes["safe.count"] = 3
    attributes["gen_ai.operation.name"] = "caller-controlled"
    attributes["error.type"] = "caller-controlled"

    telemetry.record(
        AgentSpanRecord(
            name="agent.run",
            kind=AgentSpanKind.RUN,
            started_at_ns=10,
            ended_at_ns=20,
            attributes=attributes,
        )
    )

    exported = _finished_span(exporter)
    assert exported.attributes is not None
    assert all(key not in exported.attributes for key in raw_keys)
    assert exported.attributes["safe.count"] == 3
    assert exported.attributes["gen_ai.operation.name"] == "invoke_agent"
    assert "error.type" not in exported.attributes


def test_record_without_trace_context_expect_root_span(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """No Spakky TraceContext creates a root instead of inheriting ambient OTel state."""
    telemetry, exporter, provider = telemetry_exporter
    TraceContext.clear()
    tracer = provider.get_tracer("ambient")

    with tracer.start_as_current_span("ambient-parent"):
        telemetry.record(
            AgentSpanRecord(
                name="agent.run",
                kind=AgentSpanKind.RUN,
                started_at_ns=10,
                ended_at_ns=20,
            )
        )

    spans = exporter.get_finished_spans()
    recorded = next(span for span in spans if span.name == "agent.run")
    assert recorded.parent is None


def test_default_constructor_expect_uses_global_tracer() -> None:
    """Production construction obtains the plugin's stable global tracer name."""
    tracer = trace.get_tracer("test-default")

    with patch(
        "spakky.plugins.opentelemetry.telemetry.trace.get_tracer",
        return_value=tracer,
    ) as get_tracer:
        OpenTelemetryAgentTelemetry()

    get_tracer.assert_called_once_with("spakky.agent")


def test_invalid_record_expect_core_agent_definition_error() -> None:
    """Invalid timestamps remain a core Agent contract validation failure."""
    with pytest.raises(AgentDefinitionError):
        AgentSpanRecord(
            name="agent.run",
            kind=AgentSpanKind.RUN,
            started_at_ns=20,
            ended_at_ns=10,
        )


def test_record_tampered_attribute_expect_core_agent_definition_error(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """A record corrupted after validation still fails with the core error family."""
    telemetry, _exporter, _provider = telemetry_exporter
    record = AgentSpanRecord(
        name="agent.run",
        kind=AgentSpanKind.RUN,
        started_at_ns=10,
        ended_at_ns=20,
    )
    object.__setattr__(record, "attributes", {"nested": {"raw": True}})

    with pytest.raises(AgentDefinitionError):
        telemetry.record(record)


def test_record_tampered_kind_expect_core_agent_definition_error(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """A record with a corrupted operation kind fails before span creation."""
    telemetry, exporter, _provider = telemetry_exporter
    record = AgentSpanRecord(
        name="agent.run",
        kind=AgentSpanKind.RUN,
        started_at_ns=10,
        ended_at_ns=20,
    )
    object.__setattr__(record, "kind", "invalid")

    with pytest.raises(AgentDefinitionError):
        telemetry.record(record)

    assert exporter.get_finished_spans() == ()


def test_record_tampered_error_status_expect_core_agent_definition_error(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """An error status without its required code remains a core contract error."""
    telemetry, exporter, _provider = telemetry_exporter
    record = AgentSpanRecord(
        name="agent.run",
        kind=AgentSpanKind.RUN,
        started_at_ns=10,
        ended_at_ns=20,
    )
    object.__setattr__(record, "status", AgentSpanStatus.ERROR)

    with pytest.raises(AgentDefinitionError):
        telemetry.record(record)

    assert exporter.get_finished_spans() == ()


def test_record_tampered_status_expect_core_agent_definition_error(
    telemetry_exporter: tuple[
        OpenTelemetryAgentTelemetry,
        InMemorySpanExporter,
        TracerProvider,
    ],
) -> None:
    """An unknown terminal status remains a core Agent definition failure."""
    telemetry, exporter, _provider = telemetry_exporter
    record = AgentSpanRecord(
        name="agent.run",
        kind=AgentSpanKind.RUN,
        started_at_ns=10,
        ended_at_ns=20,
    )
    object.__setattr__(record, "status", "invalid")

    with pytest.raises(AgentDefinitionError):
        telemetry.record(record)

    assert exporter.get_finished_spans() == ()
