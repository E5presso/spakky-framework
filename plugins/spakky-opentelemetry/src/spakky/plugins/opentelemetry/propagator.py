"""OTelTracePropagator — OpenTelemetry SDK bridge for ITracePropagator."""

from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator
from typing import override

from opentelemetry import context, trace
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    TraceState,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


class OTelContextConverter:
    """Convert Spakky trace state into an explicit OpenTelemetry parent context."""

    _HEX_BASE = 16

    @classmethod
    def to_otel_context(cls, trace_context: TraceContext) -> context.Context:
        """Build an OTel context containing a non-recording parent span."""
        span_context = SpanContext(
            trace_id=int(trace_context.trace_id, cls._HEX_BASE),
            span_id=int(trace_context.span_id, cls._HEX_BASE),
            is_remote=False,
            trace_flags=TraceFlags(trace_context.trace_flags),
            trace_state=TraceState(),
        )
        return trace.set_span_in_context(NonRecordingSpan(span_context))


class OTelTracePropagator(ITracePropagator):
    """Bridges Spakky's TraceContext with OpenTelemetry's context propagation.

    Converts between Spakky's contextvars-based TraceContext and OTel's
    Context system using NonRecordingSpan for lightweight propagation.
    """

    _propagator: TraceContextTextMapPropagator

    def __init__(self) -> None:
        self._propagator = TraceContextTextMapPropagator()

    @override
    def inject(self, carrier: dict[str, str]) -> None:
        """Read the ambient TraceContext and write it into the carrier.

        Converts Spakky's TraceContext to an OTel Context, then delegates
        to the W3C TraceContext propagator for header serialization.

        Args:
            carrier: Mutable header dictionary.
        """
        ctx = TraceContext.get()
        if ctx is None:
            return
        otel_ctx = OTelContextConverter.to_otel_context(ctx)
        self._propagator.inject(carrier, context=otel_ctx)

    @override
    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        """Reconstruct a TraceContext from the carrier.

        Delegates to the OTel propagator for header parsing, then converts
        the resulting OTel SpanContext back to Spakky's TraceContext.

        Args:
            carrier: Read-only header dictionary.

        Returns:
            The restored TraceContext, or None if headers are missing/invalid.
        """
        otel_ctx = self._propagator.extract(carrier)
        span = trace.get_current_span(otel_ctx)
        span_context = span.get_span_context()
        if not span_context.is_valid:
            return None
        return TraceContext(
            trace_id=format(span_context.trace_id, "032x"),
            span_id=format(span_context.span_id, "016x"),
            trace_flags=span_context.trace_flags,
        )

    @override
    def fields(self) -> list[str]:
        """Return the header field names used by this propagator.

        Returns:
            List of header names (traceparent, tracestate).
        """
        return list(self._propagator.fields)
