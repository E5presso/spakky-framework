"""Tests for OTelTracePropagator."""

from spakky.tracing.context import TraceContext

from spakky.plugins.opentelemetry.propagator import OTelTracePropagator


def test_inject_with_active_context_expect_traceparent_in_carrier() -> None:
    """활성 TraceContext가 있으면 carrier에 traceparent를 주입한다."""
    propagator = OTelTracePropagator()
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        trace_flags=1,
    )
    TraceContext.set(ctx)
    try:
        carrier: dict[str, str] = {}
        propagator.inject(carrier)

        assert "traceparent" in carrier
        assert "0af7651916cd43dd8448eb211c80319c" in carrier["traceparent"]
        assert "b7ad6b7169203331" in carrier["traceparent"]
    finally:
        TraceContext.clear()


def test_inject_without_context_expect_carrier_unchanged() -> None:
    """TraceContext가 없으면 carrier를 변경하지 않는다."""
    propagator = OTelTracePropagator()
    TraceContext.clear()

    carrier: dict[str, str] = {}
    propagator.inject(carrier)

    assert carrier == {}


def test_inject_with_unsampled_trace_expect_flags_propagated() -> None:
    """trace_flags=0 (unsampled)도 정상적으로 전파한다."""
    propagator = OTelTracePropagator()
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        trace_flags=0,
    )
    TraceContext.set(ctx)
    try:
        carrier: dict[str, str] = {}
        propagator.inject(carrier)

        assert carrier["traceparent"].endswith("-00")
    finally:
        TraceContext.clear()


def test_extract_valid_traceparent_expect_trace_context() -> None:
    """유효한 traceparent에서 TraceContext를 복원한다."""
    propagator = OTelTracePropagator()
    carrier = {
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
    }

    result = propagator.extract(carrier)

    assert result is not None
    assert result.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert result.span_id == "b7ad6b7169203331"
    assert result.trace_flags == 1


def test_extract_missing_header_expect_none() -> None:
    """traceparent 헤더가 없으면 None을 반환한다."""
    propagator = OTelTracePropagator()
    carrier: dict[str, str] = {}

    result = propagator.extract(carrier)

    assert result is None


def test_extract_invalid_traceparent_expect_none() -> None:
    """잘못된 형식의 traceparent에서 None을 반환한다."""
    propagator = OTelTracePropagator()
    carrier = {"traceparent": "invalid-header"}

    result = propagator.extract(carrier)

    assert result is None


def test_extract_unsampled_trace_expect_flags_zero() -> None:
    """trace_flags=00인 traceparent에서 flags=0을 복원한다."""
    propagator = OTelTracePropagator()
    carrier = {
        "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-00",
    }

    result = propagator.extract(carrier)

    assert result is not None
    assert result.trace_flags == 0


def test_fields_expect_traceparent_included() -> None:
    """fields()에 traceparent가 포함되어 있다."""
    propagator = OTelTracePropagator()

    result = propagator.fields()

    assert "traceparent" in result


def test_fields_expect_tracestate_included() -> None:
    """fields()에 tracestate가 포함되어 있다."""
    propagator = OTelTracePropagator()

    result = propagator.fields()

    assert "tracestate" in result


def test_inject_then_extract_expect_same_trace_context() -> None:
    """inject한 TraceContext를 extract로 동일하게 복원한다."""
    propagator = OTelTracePropagator()
    original = TraceContext(
        trace_id="abcdef1234567890abcdef1234567890",
        span_id="1234567890abcdef",
        trace_flags=1,
    )
    TraceContext.set(original)
    try:
        carrier: dict[str, str] = {}
        propagator.inject(carrier)

        restored = propagator.extract(carrier)

        assert restored is not None
        assert restored.trace_id == original.trace_id
        assert restored.span_id == original.span_id
        assert restored.trace_flags == original.trace_flags
    finally:
        TraceContext.clear()
