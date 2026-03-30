"""TraceContext — contextvars-based distributed trace context."""

import re
from contextvars import ContextVar
from secrets import token_hex
from typing import ClassVar, Self

from spakky.core.common.mutability import immutable
from spakky.tracing.error import InvalidTraceparentError

_trace_context: ContextVar["TraceContext | None"] = ContextVar(  # type: ignore[type-arg] - forward reference before class definition
    "trace_context", default=None
)


@immutable
class TraceContext:
    """W3C Trace Context Level 2 compatible trace context.

    Attributes:
        trace_id: 32-character hex string (128-bit).
        span_id: 16-character hex string (64-bit).
        parent_span_id: Parent span ID, or None for root spans.
        trace_flags: Trace flags (0x01 = sampled).
    """

    _TRACEPARENT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$"
    )
    _TRACE_ID_BYTES: ClassVar[int] = 16
    _SPAN_ID_BYTES: ClassVar[int] = 8
    _HEX_BASE: ClassVar[int] = 16

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    trace_flags: int = 1

    @classmethod
    def generate_trace_id(cls) -> str:
        """Generate a new random 128-bit trace ID as 32-character hex."""
        return token_hex(cls._TRACE_ID_BYTES)

    @classmethod
    def generate_span_id(cls) -> str:
        """Generate a new random 64-bit span ID as 16-character hex."""
        return token_hex(cls._SPAN_ID_BYTES)

    def to_traceparent(self) -> str:
        """Serialize to W3C traceparent header format.

        Returns:
            Traceparent string: ``00-{trace_id}-{span_id}-{flags:02x}``.
        """
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags:02x}"

    @classmethod
    def from_traceparent(cls, header: str) -> Self:
        """Parse a W3C traceparent header.

        Format: ``{version}-{trace_id}-{span_id}-{trace_flags}``
        Example: ``00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01``

        Args:
            header: The traceparent header value.

        Returns:
            Parsed TraceContext.

        Raises:
            InvalidTraceparentError: If the header format is invalid.
        """
        match = cls._TRACEPARENT_PATTERN.match(header.strip())
        if match is None:
            raise InvalidTraceparentError()
        _version, trace_id, span_id, flags_hex = match.groups()
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=int(flags_hex, cls._HEX_BASE),
        )

    @classmethod
    def new_root(cls) -> Self:
        """Create a new root trace (generates trace_id and span_id).

        Returns:
            A new TraceContext with fresh IDs.
        """
        return cls(
            trace_id=cls.generate_trace_id(),
            span_id=cls.generate_span_id(),
        )

    def child(self) -> Self:
        """Create a child span under this context.

        Returns:
            A new TraceContext sharing the same trace_id, with a new span_id
            and parent_span_id set to the current span_id.
        """
        return TraceContext(
            trace_id=self.trace_id,
            span_id=self.generate_span_id(),
            parent_span_id=self.span_id,
            trace_flags=self.trace_flags,
        )

    @classmethod
    def get(cls) -> Self | None:
        """Get the current execution context's TraceContext.

        Returns:
            The current TraceContext, or None if not set.
        """
        return _trace_context.get()

    @classmethod
    def set(cls, ctx: Self) -> None:
        """Set the TraceContext for the current execution context.

        Args:
            ctx: The TraceContext to set.
        """
        _trace_context.set(ctx)

    @classmethod
    def clear(cls) -> None:
        """Clear the TraceContext from the current execution context."""
        _trace_context.set(None)
