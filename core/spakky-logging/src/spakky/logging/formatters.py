"""Log formatters for Spakky Framework.

Provides three output formats:
- **Text**: Traditional human-readable single-line logs.
- **JSON**: Machine-parseable structured logs (one JSON object per line).
- **Pretty**: Coloured multi-column layout for local development.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import ClassVar

from spakky.logging.constants import (
    ANSI_DIM,
    ANSI_RESET,
    DEFAULT_DATE_FORMAT,
    LEVEL_COLORS,
    PRETTY_TIME_FORMAT,
    TEXT_SEPARATOR,
)


class SpakkyTextFormatter(logging.Formatter):
    """Human-readable single-line formatter.

    Format::

        2026-03-15T14:30:00+09:00 | INFO  | myapp.service | message
    """

    SEPARATOR: ClassVar[str] = TEXT_SEPARATOR

    def __init__(self, datefmt: str = DEFAULT_DATE_FORMAT) -> None:
        super().__init__(datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a pipe-separated text line.

        Args:
            record: The log record to format.

        Returns:
            Formatted log string.
        """
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).astimezone()
        ts_str = timestamp.strftime(self.datefmt or DEFAULT_DATE_FORMAT)

        parts = [
            ts_str,
            f"{record.levelname:<5}",
            record.name,
        ]

        context: dict[str, str] = getattr(record, "context", {})
        if context:
            ctx_str = " ".join(f"{k}={v}" for k, v in context.items())
            parts.append(ctx_str)

        parts.append(record.getMessage())

        line = self.SEPARATOR.join(parts)

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = f"{line}\n{record.exc_text}"
        if record.stack_info:
            line = f"{line}\n{record.stack_info}"
        return line


class SpakkyJsonFormatter(logging.Formatter):
    """Structured JSON formatter (one object per line).

    Output::

        {"timestamp":"...","level":"INFO","logger":"...","message":"...","context_id":"..."}
    """

    def __init__(self, datefmt: str = DEFAULT_DATE_FORMAT) -> None:
        super().__init__(datefmt=datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            JSON-encoded log string.
        """
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).astimezone()
        ts_str = timestamp.strftime(self.datefmt or DEFAULT_DATE_FORMAT)

        entry: dict[str, object] = {
            "timestamp": ts_str,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        context: dict[str, str] = getattr(record, "context", {})
        if context:
            entry.update(context)

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack_info"] = record.stack_info

        return json.dumps(entry, default=str, ensure_ascii=False)


class SpakkyPrettyFormatter(logging.Formatter):
    """Coloured multi-column formatter for local development.

    Format::

        14:30:00.123 | INFO  | myapp.service | req-abc123 |
        message text here
    """

    LEVEL_COLORS: ClassVar[dict[int, str]] = LEVEL_COLORS
    RESET: ClassVar[str] = ANSI_RESET
    DIM: ClassVar[str] = ANSI_DIM

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colours and alignment.

        Args:
            record: The log record to format.

        Returns:
            Colourised, aligned log string.
        """
        timestamp = datetime.fromtimestamp(
            record.created,
            tz=timezone.utc,
        ).astimezone()
        ts_str = timestamp.strftime(PRETTY_TIME_FORMAT) + f"{record.msecs:03.0f}"

        color = self.LEVEL_COLORS.get(record.levelno, "")
        reset = self.RESET
        dim = self.DIM

        context: dict[str, str] = getattr(record, "context", {})
        ctx_str = " ".join(f"{k}={v}" for k, v in context.items()) if context else ""

        header = (
            f"{dim}{ts_str}{reset}"
            f" {dim}|{reset}"
            f" {color}{record.levelname:<5}{reset}"
            f" {dim}|{reset}"
            f" {record.name}"
        )
        if ctx_str:
            header = f"{header} {dim}|{reset} {ctx_str}"

        message = record.getMessage()
        line = f"{header} {dim}|{reset}\n  {message}"

        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = f"{line}\n{record.exc_text}"
        if record.stack_info:
            line = f"{line}\n{record.stack_info}"
        return line
