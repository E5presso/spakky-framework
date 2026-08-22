"""OpenTelemetry sink for completed Agent telemetry records."""

from typing import override

from opentelemetry import context, trace
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from opentelemetry.util.types import AttributeValue
from spakky.agent.error import AgentDefinitionError
from spakky.agent.telemetry import (
    AgentSpanKind,
    AgentSpanRecord,
    AgentSpanStatus,
    IAgentTelemetry,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.tracing.context import TraceContext

from spakky.plugins.opentelemetry.propagator import OTelContextConverter


@Pod()
class OpenTelemetryAgentTelemetry(IAgentTelemetry):
    """Record privacy-safe completed Agent operations as OpenTelemetry spans."""

    _TRACER_NAME = "spakky.agent"
    _GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
    _ERROR_TYPE = "error.type"
    _RAW_BODY_ATTRIBUTE_KEYS = frozenset(
        {
            "context",
            "gen_ai.completion",
            "gen_ai.input.messages",
            "gen_ai.output.messages",
            "gen_ai.prompt",
            "gen_ai.retrieval.documents",
            "gen_ai.retrieval.query.text",
            "gen_ai.system_instructions",
            "gen_ai.tool.call.arguments",
            "gen_ai.tool.call.result",
            "prompt",
            "tool.result",
            "tool_result",
        }
    )
    _RESERVED_ATTRIBUTE_KEYS = frozenset({_ERROR_TYPE, _GEN_AI_OPERATION_NAME})

    __tracer: Tracer

    def __init__(self, tracer: Tracer | None = None) -> None:
        self.__tracer = (
            tracer if tracer is not None else trace.get_tracer(self._TRACER_NAME)
        )

    @override
    def record(self, span: AgentSpanRecord) -> None:
        """Create and end one OTel span using the record's exact timestamps."""
        operation_name, span_kind = self._operation(span.kind)
        attributes = self._attributes(span, operation_name)
        status = self._status(span)
        parent_context = self._parent_context()
        otel_span = self.__tracer.start_span(
            span.name,
            context=parent_context,
            kind=span_kind,
            attributes=attributes,
            start_time=span.started_at_ns,
        )
        try:
            otel_span.set_status(status)
        finally:
            otel_span.end(end_time=span.ended_at_ns)

    @classmethod
    def _operation(cls, kind: AgentSpanKind) -> tuple[str, SpanKind]:
        match kind:
            case AgentSpanKind.RUN:
                return "invoke_agent", SpanKind.INTERNAL
            case AgentSpanKind.MODEL:
                return "generate_content", SpanKind.CLIENT
            case AgentSpanKind.TOOL:
                return "execute_tool", SpanKind.INTERNAL
            case AgentSpanKind.RETRIEVAL:
                return "retrieval", SpanKind.CLIENT
            case _:
                raise AgentDefinitionError("Agent telemetry span kind is invalid")

    @classmethod
    def _attributes(
        cls,
        span: AgentSpanRecord,
        operation_name: str,
    ) -> dict[str, AttributeValue]:
        attributes: dict[str, AttributeValue] = {}
        for key, value in span.attributes.items():
            normalized_key = key.casefold()
            if (
                normalized_key in cls._RAW_BODY_ATTRIBUTE_KEYS
                or normalized_key in cls._RESERVED_ATTRIBUTE_KEYS
            ):
                continue
            if not isinstance(value, str | bool | int | float):
                raise AgentDefinitionError(
                    "Agent telemetry attributes must contain scalar values"
                )
            attributes[key] = value
        attributes[cls._GEN_AI_OPERATION_NAME] = operation_name
        if span.error_code is not None:
            attributes[cls._ERROR_TYPE] = span.error_code
        return attributes

    @staticmethod
    def _parent_context() -> context.Context:
        trace_context = TraceContext.get()
        if trace_context is None:
            return context.Context()
        return OTelContextConverter.to_otel_context(trace_context)

    @staticmethod
    def _status(span: AgentSpanRecord) -> Status:
        match span.status:
            case AgentSpanStatus.OK:
                return Status(StatusCode.OK)
            case AgentSpanStatus.ERROR:
                error_code = span.error_code
                if error_code is None:
                    raise AgentDefinitionError(
                        "Agent telemetry error status requires exactly one error code"
                    )
                return Status(StatusCode.ERROR, error_code)
            case _:
                raise AgentDefinitionError("Agent telemetry span status is invalid")
