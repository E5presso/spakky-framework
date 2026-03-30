"""ITracePropagator — trace context propagation interface."""

from abc import ABC, abstractmethod

from spakky.tracing.context import TraceContext


class ITracePropagator(ABC):
    """Interface for trace context propagation across service boundaries.

    Implementations read/write the ambient ``TraceContext`` (stored in
    ``contextvars``) from/to carrier dictionaries such as HTTP headers
    or message metadata.

    Terminology follows the OpenTelemetry ``TextMapPropagator`` convention:

    * **inject** — read the ambient ``TraceContext`` and write it into an
      outbound carrier.  Does **not** create a new trace; it serializes
      whatever context is currently active.  If no context is active the
      carrier is left unchanged.
    * **extract** — read an inbound carrier and reconstruct a
      ``TraceContext``.  The caller is responsible for activating it via
      ``TraceContext.set()``.
    """

    @abstractmethod
    def inject(self, carrier: dict[str, str]) -> None:
        """Read the ambient TraceContext and write it into the carrier.

        This is an **upsert** on the carrier: if a context is active its
        header fields are added (or overwritten); if no context is active
        the carrier is left untouched.

        Args:
            carrier: Mutable header dictionary.  After the call, keys such
                as ``traceparent`` may be present.
        """
        ...

    @abstractmethod
    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        """Reconstruct a TraceContext from the carrier.

        The returned context is **not** automatically activated.  Call
        ``TraceContext.set()`` to make it the ambient context.

        Args:
            carrier: Read-only header dictionary.

        Returns:
            The restored TraceContext, or None if the required headers are
            missing or malformed.
        """
        ...

    @abstractmethod
    def fields(self) -> list[str]:
        """Return the header field names used by this propagator.

        Returns:
            List of header names, e.g., ``["traceparent", "tracestate"]``.
        """
        ...
