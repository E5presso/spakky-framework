"""ITracePropagator — trace context propagation interface."""

from abc import ABC, abstractmethod

from spakky.tracing.context import TraceContext


class ITracePropagator(ABC):
    """Interface for trace context propagation across service boundaries.

    Implementations inject/extract TraceContext into/from carrier dictionaries
    (e.g., HTTP headers, message metadata).
    """

    @abstractmethod
    def inject(self, carrier: dict[str, str]) -> None:
        """Write the current TraceContext into the carrier.

        Args:
            carrier: Mutable header dictionary. After injection, keys like
                ``traceparent`` are added.
        """
        ...

    @abstractmethod
    def extract(self, carrier: dict[str, str]) -> TraceContext | None:
        """Restore a TraceContext from the carrier.

        Args:
            carrier: Read-only header dictionary.

        Returns:
            The restored TraceContext, or None if the header is missing or
            parsing fails.
        """
        ...

    @abstractmethod
    def fields(self) -> list[str]:
        """Return the header field names used by this propagator.

        Returns:
            List of header names, e.g., ``["traceparent", "tracestate"]``.
        """
        ...
