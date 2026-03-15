"""Shared constants for the spakky-logging package."""

from __future__ import annotations

# --- Configuration ---

SPAKKY_LOGGING_CONFIG_ENV_PREFIX: str = "SPAKKY_LOGGING__"

# --- ContextVar ---

LOG_CONTEXT_VAR_NAME: str = "__spakky_log_context__"

# --- Handler ---

HANDLER_NAME: str = "__spakky_logging_handler__"

# --- Timestamp ---

DEFAULT_DATE_FORMAT: str = "%Y-%m-%dT%H:%M:%S%z"

# --- Masking ---

DEFAULT_MASK_KEYS: list[str] = ["password", "secret", "token", "key"]
DEFAULT_MASK_REPLACEMENT: str = "******"
MASKING_REGEX: str = r"((['\"]?(?={keys})[^'\"]*['\"]?[:=]\s*)['\"][^'\"]*['\"])"
MASKING_REPLACEMENT: str = r"\2'******'"

# --- Thresholds ---

DEFAULT_SLOW_THRESHOLD_MS: float = 1000.0
DEFAULT_MAX_RESULT_LENGTH: int = 200

# --- Formatter ---

TEXT_SEPARATOR: str = " | "

LEVEL_COLORS: dict[int, str] = {
    10: "\033[36m",  # DEBUG — cyan
    20: "\033[32m",  # INFO — green
    30: "\033[33m",  # WARNING — yellow
    40: "\033[31m",  # ERROR — red
    50: "\033[35m",  # CRITICAL — magenta
}
ANSI_RESET: str = "\033[0m"
ANSI_DIM: str = "\033[2m"

PRETTY_TIME_FORMAT: str = "%H:%M:%S."
