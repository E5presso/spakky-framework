"""Log context management using contextvars.

Provides a thread-safe and async-safe mechanism for binding
contextual key-value pairs to log records. Bound values are
automatically available to all loggers within the same execution
context (asyncio task or thread).
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from spakky.plugins.logging.constants import LOG_CONTEXT_VAR_NAME

_log_context: ContextVar[dict[str, str]] = ContextVar(
    LOG_CONTEXT_VAR_NAME,
    default={},
)


class LogContext:
    """Manages contextual key-value pairs for structured logging.

    Values bound via :meth:`bind` are propagated through ``contextvars``
    and injected into every log record by :class:`ContextInjectingFilter`.
    """

    @classmethod
    def bind(cls, **kwargs: str) -> None:
        """Add key-value pairs to the current log context.

        Args:
            **kwargs: Key-value pairs to bind.
        """
        current = _log_context.get().copy()
        current.update(kwargs)
        _log_context.set(current)

    @classmethod
    def unbind(cls, *keys: str) -> None:
        """Remove keys from the current log context.

        Args:
            *keys: Keys to remove.
        """
        current = _log_context.get().copy()
        for key in keys:
            current.pop(key, None)
        _log_context.set(current)

    @classmethod
    def clear(cls) -> None:
        """Remove all key-value pairs from the current log context."""
        _log_context.set({})

    @classmethod
    def get(cls) -> dict[str, str]:
        """Return a copy of the current log context.

        Returns:
            Current context key-value pairs.
        """
        return _log_context.get().copy()

    @classmethod
    @contextmanager
    def scope(cls, **kwargs: str) -> Generator[None]:
        """Temporarily bind values for the duration of a ``with`` block.

        Previous context is restored when the block exits.

        Args:
            **kwargs: Key-value pairs to bind within the scope.

        Yields:
            None
        """
        previous = _log_context.get().copy()
        merged = {**previous, **kwargs}
        _log_context.set(merged)
        try:
            yield
        finally:
            _log_context.set(previous)
