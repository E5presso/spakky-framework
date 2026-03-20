"""W3CTracePropagator — W3C Trace Context Level 2 propagator."""

from spakky.core.pod.annotations.pod import Pod
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator

TRACEPARENT_HEADER = "traceparent"


@Pod()
class W3CTracePropagator(ITracePropagator):
    """W3C Trace Context Level 2 standard propagator.

    Pure Python implementation with no external dependencies.
    traceparent format: ``{version:2}-{trace_id:32}-{span_id:16}-{trace_flags:2}``
    """

    def inject(self, carrier: dict[str, str]) -> None:
        """Write the current TraceContext as a traceparent header into the carrier.

        Args:
            carrier: Mutable header dictionary.
        """
        ctx = TraceContext.get()
        if ctx is not None:
            carrier[TRACEPARENT_HEADER] = ctx.to_traceparent()

    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        """Restore a TraceContext from the traceparent header in the carrier.

        Args:
            carrier: Read-only header dictionary.

        Returns:
            The restored TraceContext, or None if the header is missing or invalid.
        """
        header = carrier.get(TRACEPARENT_HEADER)
        if header is None:
            return None
        try:
            return TraceContext.from_traceparent(header)
        except Exception:  # pragma: no branch - InvalidTraceparentError 외 방어
            return None

    def fields(self) -> list[str]:
        """Return the header field names used by this propagator.

        Returns:
            ``["traceparent"]``
        """
        return [TRACEPARENT_HEADER]
