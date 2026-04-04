"""Tests for LogContextBridge."""

from unittest.mock import MagicMock

from spakky.core.logging.interfaces.log_context_binder import ILogContextBinder
from spakky.tracing.context import TraceContext

from spakky.plugins.opentelemetry.bridge import LogContextBridge


def test_sync_with_active_trace_expect_log_context_bound() -> None:
    """활성 TraceContext가 있으면 binder.bind()로 trace_id/span_id를 바인딩한다."""
    binder = MagicMock(spec=ILogContextBinder)
    bridge = LogContextBridge(binder=binder)
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
    )
    TraceContext.set(ctx)
    try:
        bridge.sync()

        binder.bind.assert_called_once_with(
            trace_id="0af7651916cd43dd8448eb211c80319c",
            span_id="b7ad6b7169203331",
        )
    finally:
        TraceContext.clear()


def test_sync_without_trace_expect_log_context_unbound() -> None:
    """TraceContext가 없으면 binder.unbind()로 trace_id/span_id를 제거한다."""
    binder = MagicMock(spec=ILogContextBinder)
    bridge = LogContextBridge(binder=binder)
    TraceContext.clear()

    bridge.sync()

    binder.unbind.assert_called_once_with("trace_id", "span_id")


def test_sync_on_context_change_expect_log_context_updated() -> None:
    """TraceContext 변경 후 sync()를 호출하면 binder.bind()가 새 값으로 호출된다."""
    binder = MagicMock(spec=ILogContextBinder)
    bridge = LogContextBridge(binder=binder)
    ctx1 = TraceContext(
        trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
        span_id="bbbbbbbbbbbbbb01",
    )
    ctx2 = TraceContext(
        trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2",
        span_id="bbbbbbbbbbbbbb02",
    )
    try:
        TraceContext.set(ctx1)
        bridge.sync()
        binder.bind.assert_called_with(
            trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1",
            span_id="bbbbbbbbbbbbbb01",
        )

        TraceContext.set(ctx2)
        bridge.sync()
        binder.bind.assert_called_with(
            trace_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2",
            span_id="bbbbbbbbbbbbbb02",
        )
    finally:
        TraceContext.clear()


def test_sync_without_binder_expect_noop() -> None:
    """binder가 None이면 sync()는 아무 동작도 하지 않는다."""
    bridge = LogContextBridge()
    ctx = TraceContext(
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
    )
    TraceContext.set(ctx)
    try:
        bridge.sync()  # Should not raise
    finally:
        TraceContext.clear()
