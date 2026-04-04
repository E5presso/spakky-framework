"""LogContextBridge — optional trace-to-logging context synchronization."""

from spakky.tracing.context import TraceContext

try:
    from spakky.plugins.logging.context import LogContext

    _HAS_LOGGING = True
except ImportError:  # pragma: no cover - optional dependency (spakky-logging)
    _HAS_LOGGING = False


class LogContextBridge:
    """Synchronizes TraceContext fields into LogContext.

    When spakky-logging is installed, ``sync()`` binds the current
    trace_id and span_id into the structured logging context.
    When spakky-logging is not installed, all operations are no-ops.
    """

    @staticmethod
    def sync() -> None:
        """Bind current TraceContext's trace_id/span_id into LogContext.

        If no TraceContext is active, unbinds trace fields from LogContext.
        """
        if not _HAS_LOGGING:
            return  # pragma: no cover - optional dependency (spakky-logging)
        ctx = TraceContext.get()
        if ctx is not None:
            LogContext.bind(trace_id=ctx.trace_id, span_id=ctx.span_id)
        else:
            LogContext.unbind("trace_id", "span_id")
