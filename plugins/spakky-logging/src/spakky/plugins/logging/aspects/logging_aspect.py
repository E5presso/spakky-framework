"""Logging aspects for automatic method call logging with masking and timing.

Provides sync and async AOP aspects that intercept methods annotated
with ``@Logging`` and emit structured log messages including:

- Method name and arguments (with sensitive data masking)
- Return value (truncated to ``max_result_length``)
- Execution duration
- Slow-call warnings when ``slow_threshold_ms`` is exceeded
"""

from __future__ import annotations

import re
from inspect import iscoroutinefunction
from logging import WARNING, getLogger
from time import perf_counter
from typing import Any, ClassVar

from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order

from spakky.plugins.logging.annotation import Logged
from spakky.plugins.logging.config import LoggingConfig
from spakky.plugins.logging.constants import (
    DEFAULT_MASK_KEYS,
    DEFAULT_MAX_RESULT_LENGTH,
    DEFAULT_SLOW_THRESHOLD_MS,
    MASKING_REGEX,
    MASKING_REPLACEMENT,
)

logger = getLogger(__name__)


def _build_mask(keys: list[str]) -> re.Pattern[str]:
    joined = "|".join(re.escape(k) for k in keys)
    return re.compile(MASKING_REGEX.format(keys=joined))


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _format_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    parts: list[str] = []
    if args:
        parts.extend(f"{arg!r}" for arg in args)
    if kwargs:
        parts.extend(f"{key}={value!r}" for key, value in kwargs.items())
    return ", ".join(parts)


@Order(0)
@AsyncAspect()
class AsyncLoggingAspect(IAsyncAspect):
    """Aspect for logging async method calls with execution time and data masking."""

    _config: LoggingConfig | None

    def __init__(self, config: LoggingConfig | None = None) -> None:
        """Initialize the async logging aspect.

        Args:
            config: Optional logging configuration. Uses defaults if None.
        """
        self._config = config

    MASKING_TEXT: ClassVar[str] = MASKING_REPLACEMENT

    @Around(lambda x: Logged.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self,
        joinpoint: AsyncFunc,
        *args: Any,
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Log async method execution with timing and masking.

        Args:
            joinpoint: The async method being intercepted.
            *args: Positional arguments to the method.
            **kwargs: Keyword arguments to the method.

        Returns:
            The result of the method execution.

        Raises:
            Exception: Re-raises any exception after logging it.
        """
        annotation: Logged = Logged.get(joinpoint)
        mask_keys = annotation.masking_keys or (
            self._config.mask_keys if self._config else DEFAULT_MASK_KEYS
        )
        mask = _build_mask(mask_keys)
        slow_threshold = annotation.slow_threshold_ms or (
            self._config.slow_threshold_ms
            if self._config
            else DEFAULT_SLOW_THRESHOLD_MS
        )
        max_result_length = annotation.max_result_length or (
            self._config.max_result_length
            if self._config
            else DEFAULT_MAX_RESULT_LENGTH
        )

        formatted_args = _format_args(args, kwargs) if annotation.log_args else "..."

        start: float = perf_counter()
        try:
            result = await joinpoint(*args, **kwargs)
        except Exception as e:
            elapsed_ms = (perf_counter() - start) * 1000
            error_msg = (
                f"[{type(self).__name__}] "
                f"{joinpoint.__qualname__}({formatted_args}) "
                f"raised {type(e).__name__} ({elapsed_ms:.2f}ms)"
            )
            logger.error(
                mask.sub(self.MASKING_TEXT, error_msg)
                if annotation.enable_masking
                else error_msg,
            )
            raise

        elapsed_ms = (perf_counter() - start) * 1000
        result_repr = (
            _truncate(repr(result), max_result_length)
            if annotation.log_result
            else "..."
        )
        msg = (
            f"[{type(self).__name__}] "
            f"{joinpoint.__qualname__}({formatted_args}) "
            f"-> {result_repr} ({elapsed_ms:.2f}ms)"
        )
        log_msg = mask.sub(self.MASKING_TEXT, msg) if annotation.enable_masking else msg

        if elapsed_ms >= slow_threshold:
            logger.log(WARNING, "[SLOW] %s", log_msg)
        else:
            logger.info(log_msg)

        return result


@Order(0)
@Aspect()
class LoggingAspect(IAspect):
    """Aspect for logging synchronous method calls with execution time and data masking."""

    _config: LoggingConfig | None

    def __init__(self, config: LoggingConfig | None = None) -> None:
        """Initialize the sync logging aspect.

        Args:
            config: Optional logging configuration. Uses defaults if None.
        """
        self._config = config

    MASKING_TEXT: ClassVar[str] = MASKING_REPLACEMENT

    @Around(lambda x: Logged.exists(x) and not iscoroutinefunction(x))
    def around(
        self,
        joinpoint: Func,
        *args: Any,
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Log sync method execution with timing and masking.

        Args:
            joinpoint: The sync method being intercepted.
            *args: Positional arguments to the method.
            **kwargs: Keyword arguments to the method.

        Returns:
            The result of the method execution.

        Raises:
            Exception: Re-raises any exception after logging it.
        """
        annotation: Logged = Logged.get(joinpoint)
        mask_keys = annotation.masking_keys or (
            self._config.mask_keys if self._config else DEFAULT_MASK_KEYS
        )
        mask = _build_mask(mask_keys)
        slow_threshold = annotation.slow_threshold_ms or (
            self._config.slow_threshold_ms
            if self._config
            else DEFAULT_SLOW_THRESHOLD_MS
        )
        max_result_length = annotation.max_result_length or (
            self._config.max_result_length
            if self._config
            else DEFAULT_MAX_RESULT_LENGTH
        )

        formatted_args = _format_args(args, kwargs) if annotation.log_args else "..."

        start: float = perf_counter()
        try:
            result = joinpoint(*args, **kwargs)
        except Exception as e:
            elapsed_ms = (perf_counter() - start) * 1000
            error_msg = (
                f"[{type(self).__name__}] "
                f"{joinpoint.__qualname__}({formatted_args}) "
                f"raised {type(e).__name__} ({elapsed_ms:.2f}ms)"
            )
            logger.error(
                mask.sub(self.MASKING_TEXT, error_msg)
                if annotation.enable_masking
                else error_msg,
            )
            raise

        elapsed_ms = (perf_counter() - start) * 1000
        result_repr = (
            _truncate(repr(result), max_result_length)
            if annotation.log_result
            else "..."
        )
        msg = (
            f"[{type(self).__name__}] "
            f"{joinpoint.__qualname__}({formatted_args}) "
            f"-> {result_repr} ({elapsed_ms:.2f}ms)"
        )
        log_msg = mask.sub(self.MASKING_TEXT, msg) if annotation.enable_masking else msg

        if elapsed_ms >= slow_threshold:
            logger.log(WARNING, "[SLOW] %s", log_msg)
        else:
            logger.info(log_msg)

        return result
