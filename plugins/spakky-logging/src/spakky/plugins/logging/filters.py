"""Logging filter that injects LogContext values into log records.

Attaches all key-value pairs from the current :class:`LogContext`
as attributes on every :class:`logging.LogRecord`, making them
available to formatters.
"""

from __future__ import annotations

import logging

from spakky.plugins.logging.context import LogContext


class ContextInjectingFilter(logging.Filter):
    """Filter that injects :class:`LogContext` values into log records.

    When added to a logger or handler, every record will carry the
    current context as extra attributes and a consolidated ``context``
    dict attribute.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Inject context values into the log record.

        Args:
            record: The log record to augment.

        Returns:
            Always ``True`` — this filter never suppresses records.
        """
        context = LogContext.get()
        record.context = context  # type: ignore[attr-defined]
        for key, value in context.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True
