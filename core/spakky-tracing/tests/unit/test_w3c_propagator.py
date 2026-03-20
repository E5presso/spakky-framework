"""Unit tests for W3CTracePropagator."""

from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import TRACEPARENT_HEADER, W3CTracePropagator


def test_inject_with_context_expect_traceparent_in_carrier() -> None:
    """TraceContext가 있을 때 carrier에 traceparent 헤더가 추가되는지 검증한다."""
    propagator = W3CTracePropagator()
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        trace_flags=1,
    )
    TraceContext.set(ctx)

    carrier: dict[str, str] = {}
    propagator.inject(carrier)

    assert (
        carrier[TRACEPARENT_HEADER]
        == "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    )
    TraceContext.clear()


def test_inject_without_context_expect_carrier_unchanged() -> None:
    """TraceContext가 없을 때 carrier가 변경되지 않는지 검증한다."""
    TraceContext.clear()
    propagator = W3CTracePropagator()

    carrier: dict[str, str] = {}
    propagator.inject(carrier)

    assert carrier == {}


def test_extract_valid_header_expect_trace_context() -> None:
    """유효한 traceparent 헤더에서 TraceContext가 복원되는지 검증한다."""
    propagator = W3CTracePropagator()
    carrier = {
        TRACEPARENT_HEADER: "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }

    ctx = propagator.extract(carrier)

    assert ctx is not None
    assert ctx.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert ctx.span_id == "b7ad6b7169203331"
    assert ctx.trace_flags == 1


def test_extract_missing_header_expect_none() -> None:
    """traceparent 헤더가 없을 때 None이 반환되는지 검증한다."""
    propagator = W3CTracePropagator()
    carrier: dict[str, str] = {}

    ctx = propagator.extract(carrier)

    assert ctx is None


def test_extract_invalid_header_expect_none() -> None:
    """잘못된 형식의 traceparent 헤더에서 None이 반환되는지 검증한다."""
    propagator = W3CTracePropagator()
    carrier = {TRACEPARENT_HEADER: "not-a-valid-traceparent"}

    ctx = propagator.extract(carrier)

    assert ctx is None


def test_fields_expect_traceparent() -> None:
    """fields()가 ["traceparent"]를 반환하는지 검증한다."""
    propagator = W3CTracePropagator()

    assert propagator.fields() == [TRACEPARENT_HEADER]
