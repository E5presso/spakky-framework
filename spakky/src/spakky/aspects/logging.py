"""Logging aspect for automatic method call logging with sensitive data masking.

This module provides @Logging annotation and corresponding aspects for
automatic logging of method calls with execution time and optional data masking.
"""

import re
from dataclasses import dataclass, field
from inspect import iscoroutinefunction
from logging import getLogger
from time import perf_counter
from typing import Any, ClassVar

from spakky.aop.aspect import Aspect, AsyncAspect
from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.aop.pointcut import Around
from spakky.core.annotation import FunctionAnnotation
from spakky.core.types import AsyncFunc, Func
from spakky.pod.annotations.order import Order

logger = getLogger(__name__)


@dataclass
class Logging(FunctionAnnotation):
    """Annotation for enabling automatic method logging.

    Methods decorated with @Logging() will have their calls, arguments,
    return values, and execution time automatically logged.
    """

    enable_masking: bool = True
    """Whether to mask sensitive data in logs."""

    masking_keys: list[str] = field(
        default_factory=lambda: ["secret", "key", "password"]
    )
    """List of keys whose values should be masked in logs."""


@Order(0)
@AsyncAspect()
class AsyncLoggingAspect(IAsyncAspect):
    """Aspect for logging async method calls with execution time and data masking.

    Intercepts async methods decorated with @Logging and logs:
    - Method name and arguments
    - Return value or exception
    - Execution time
    - Masked sensitive data (if enabled)
    """

    MASKING_TEXT: ClassVar[str] = r"\2'******'"
    """Replacement text for masked sensitive values."""

    MASKING_REGEX: ClassVar[str] = (
        r"((['\"]?(?={keys})[^'\"]*['\"]?[:=]\s*)['\"][^'\"]*['\"])"
    )
    """Regex pattern for detecting sensitive key-value pairs."""

    @Around(lambda x: Logging.exists(x) and iscoroutinefunction(x))
    async def around_async(
        self, joinpoint: AsyncFunc, *args: Any, **kwargs: Any
    ) -> Any:
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
        start: float = perf_counter()
        annotation: Logging = Logging.get(joinpoint)
        masking_keys: str = "|".join(annotation.masking_keys)
        masking_regex: str = self.MASKING_REGEX.format(keys=masking_keys)
        mask: re.Pattern[str] = re.compile(masking_regex)
        _args: str = ", ".join(f"{arg!r}" for arg in args) if any(args) else ""
        _kwargs: str = (
            ", ".join(f"{key}={value!r}" for key, value in kwargs.items())
            if any(kwargs)
            else ""
        )

        try:
            result = await joinpoint(*args, **kwargs)
        except Exception as e:
            end: float = perf_counter()
            error: str = f"[{type(self).__name__}] {joinpoint.__qualname__}({_args}{_kwargs}) raised {type(e).__name__} ({end - start:.2f}s)"
            logger.error(
                mask.sub(self.MASKING_TEXT, error)
                if annotation.enable_masking
                else error
            )
            raise
        end: float = perf_counter()
        after: str = f"[{type(self).__name__}] {joinpoint.__qualname__}({_args}{_kwargs}) -> {result!r} ({end - start:.2f}s)"
        logger.info(
            mask.sub(self.MASKING_TEXT, after) if annotation.enable_masking else after
        )
        return result


@Order(0)
@Aspect()
class LoggingAspect(IAspect):
    """Aspect for logging synchronous method calls with execution time and data masking.

    Intercepts sync methods decorated with @Logging and logs:
    - Method name and arguments
    - Return value or exception
    - Execution time
    - Masked sensitive data (if enabled)
    """

    MASKING_TEXT: ClassVar[str] = r"\2'******'"
    """Replacement text for masked sensitive values."""

    MASKING_REGEX: ClassVar[str] = (
        r"((['\"]?(?={keys})[^'\"]*['\"]?[:=]\s*)['\"][^'\"]*['\"])"
    )
    """Regex pattern for detecting sensitive key-value pairs."""

    @Around(lambda x: Logging.exists(x) and not iscoroutinefunction(x))
    def around(self, joinpoint: Func, *args: Any, **kwargs: Any) -> Any:
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
        start: float = perf_counter()
        annotation: Logging = Logging.get(joinpoint)
        masking_keys: str = "|".join(annotation.masking_keys)
        masking_regex: str = self.MASKING_REGEX.format(keys=masking_keys)
        mask: re.Pattern[str] = re.compile(masking_regex)
        _args: str = ", ".join(f"{arg!r}" for arg in args) if any(args) else ""
        _kwargs: str = (
            ", ".join(f"{key}={value!r}" for key, value in kwargs.items())
            if any(kwargs)
            else ""
        )

        try:
            result = joinpoint(*args, **kwargs)
        except Exception as e:
            end: float = perf_counter()
            error: str = f"[{type(self).__name__}] {joinpoint.__qualname__}({_args}{_kwargs}) raised {type(e).__name__} ({end - start:.2f}s)"
            logger.error(
                mask.sub(self.MASKING_TEXT, error)
                if annotation.enable_masking
                else error
            )
            raise
        end: float = perf_counter()
        after: str = f"[{type(self).__name__}] {joinpoint.__qualname__}({_args}{_kwargs}) -> {result!r} ({end - start:.2f}s)"
        logger.info(
            mask.sub(self.MASKING_TEXT, after) if annotation.enable_masking else after
        )
        return result
