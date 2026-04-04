"""Tests for LogContextBridge."""

from spakky.plugins.logging.context import LogContext
from spakky.tracing.context import TraceContext

from spakky.plugins.opentelemetry.bridge import LogContextBridge


def test_sync_with_active_trace_expect_log_context_bound() -> None:
    """활성 TraceContext가 있으면 LogContext에 trace_id/span_id를 바인딩한다."""
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
    )
    TraceContext.set(ctx)
    LogContext.clear()
    try:
        LogContextBridge.sync()

        log_ctx = LogContext.get()
        assert log_ctx["trace_id"] == "0af7651916cd43dd8448eb211c80319c"
        assert log_ctx["span_id"] == "b7ad6b7169203331"
    finally:
        TraceContext.clear()
        LogContext.clear()


def test_sync_without_trace_expect_log_context_unbound() -> None:
    """TraceContext가 없으면 LogContext에서 trace_id/span_id를 제거한다."""
    LogContext.bind(trace_id="old-trace", span_id="old-span")
    TraceContext.clear()
    try:
        LogContextBridge.sync()

        log_ctx = LogContext.get()
        assert "trace_id" not in log_ctx
        assert "span_id" not in log_ctx
    finally:
        LogContext.clear()


def test_sync_updates_on_context_change() -> None:
    """TraceContext 변경 후 sync()를 호출하면 LogContext가 갱신된다."""
    ctx1 = TraceContext(
        trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
        span_id="bbbbbbbbbbbbbb01",
    )
    ctx2 = TraceContext(
        trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2",
        span_id="bbbbbbbbbbbbbb02",
    )
    LogContext.clear()
    try:
        TraceContext.set(ctx1)
        LogContextBridge.sync()
        assert LogContext.get()["trace_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1"

        TraceContext.set(ctx2)
        LogContextBridge.sync()
        assert LogContext.get()["trace_id"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2"
    finally:
        TraceContext.clear()
        LogContext.clear()
