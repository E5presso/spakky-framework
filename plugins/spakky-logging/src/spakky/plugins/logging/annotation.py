"""Logging annotation for automatic method call logging."""

from dataclasses import dataclass, field
from typing import Callable, ParamSpec, TypeVar

from spakky.core.common.annotation import FunctionAnnotation

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Logged(FunctionAnnotation):
    """Annotation for enabling automatic method logging.

    Methods decorated with ``@Logging()`` will have their calls, arguments,
    return values, and execution time automatically logged.

    Attributes:
        enable_masking: Whether to mask sensitive data in logs.
        masking_keys: List of keys whose values should be masked.
            When empty, the global :attr:`LoggingConfig.mask_keys` is used.
        slow_threshold_ms: Per-method slow-call warning threshold.
            ``None`` falls back to :attr:`LoggingConfig.slow_threshold_ms`.
        max_result_length: Maximum repr length for the return value.
            ``None`` falls back to :attr:`LoggingConfig.max_result_length`.
        log_args: Whether to include arguments in the log message.
        log_result: Whether to include the return value in the log message.
    """

    enable_masking: bool = True
    """Whether to mask sensitive data in logs."""

    masking_keys: list[str] = field(default_factory=list)
    """Keys whose values should be masked. Empty = use global config."""

    slow_threshold_ms: float | None = None
    """Per-method slow-call threshold (ms). None = use global config."""

    max_result_length: int | None = None
    """Max repr length for return values. None = use global config."""

    log_args: bool = True
    """Whether to include arguments in log output."""

    log_result: bool = True
    """Whether to include the return value in log output."""


def logged(
    enable_masking: bool = True,
    masking_keys: list[str] | None = None,
    slow_threshold_ms: float | None = None,
    max_result_length: int | None = None,
    log_args: bool = True,
    log_result: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator for enabling automatic method logging.

    Args:
        enable_masking: Whether to mask sensitive data in logs.
        masking_keys: List of keys whose values should be masked.
            When empty, the global :attr:`LoggingConfig.mask_keys` is used.
        slow_threshold_ms: Per-method slow-call warning threshold.
            ``None`` falls back to :attr:`LoggingConfig.slow_threshold_ms`.
        max_result_length: Maximum repr length for the return value.
            ``None`` falls back to :attr:`LoggingConfig.max_result_length`.
        log_args: Whether to include arguments in the log message.
        log_result: Whether to include the return value in the log message.

    Returns:
        A decorator that applies the logging annotation to a method.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return Logged(
            enable_masking=enable_masking,
            masking_keys=masking_keys or [],
            slow_threshold_ms=slow_threshold_ms,
            max_result_length=max_result_length,
            log_args=log_args,
            log_result=log_result,
        )(func)

    return decorator
