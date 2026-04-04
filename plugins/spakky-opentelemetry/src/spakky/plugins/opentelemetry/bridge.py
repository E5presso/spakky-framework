"""LogContextBridge — optional trace-to-logging context synchronization."""

from spakky.core.logging.interfaces.log_context_binder import ILogContextBinder
from spakky.core.pod.annotations.pod import Pod
from spakky.tracing.context import TraceContext


@Pod()
class LogContextBridge:
    """Synchronizes TraceContext fields into LogContext.

    When an ``ILogContextBinder`` is available (i.e., spakky-logging is
    installed and registered), ``sync()`` binds the current trace_id
    and span_id into the structured logging context.
    When no binder is available, all operations are no-ops.
    """

    __binder: ILogContextBinder | None

    def __init__(self, binder: ILogContextBinder | None = None) -> None:
        self.__binder = binder

    def sync(self) -> None:
        """Bind current TraceContext's trace_id/span_id into LogContext.

        If no ``ILogContextBinder`` was injected, this is a no-op.
        If no TraceContext is active, unbinds trace fields.
        """
        if self.__binder is None:
            return
        ctx = TraceContext.get()
        if ctx is not None:
            self.__binder.bind(trace_id=ctx.trace_id, span_id=ctx.span_id)
        else:
            self.__binder.unbind("trace_id", "span_id")
