"""Protocol interfaces for aspect implementations.

This module defines the protocols that aspect classes must implement to intercept
method calls in the AOP system.
"""

from typing import Any, Protocol, TypeVar, runtime_checkable

from spakky.core.types import AsyncFunc, Func


@runtime_checkable
class IAspect(Protocol):
    """Protocol for synchronous aspect implementations."""

    def before(self, *args: Any, **kwargs: Any) -> None:
        """Execute before the target method is called.

        Args:
            *args: Positional arguments for the target method.
            **kwargs: Keyword arguments for the target method.
        """
        return

    def after_raising(self, error: Exception) -> None:
        """Execute after the target method raises an exception.

        Args:
            error: The exception that was raised.
        """
        return

    def after_returning(self, result: Any) -> None:
        """Execute after the target method returns successfully.

        Args:
            result: The return value from the target method.
        """
        return

    def after(self) -> None:
        """Execute after the target method completes (regardless of outcome)."""
        return

    def around(
        self,
        joinpoint: Func,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Wrap around the target method execution.

        Args:
            joinpoint: The target method to be executed.
            *args: Positional arguments for the target method.
            **kwargs: Keyword arguments for the target method.

        Returns:
            The result of the joinpoint execution.
        """
        return joinpoint(*args, **kwargs)


@runtime_checkable
class IAsyncAspect(Protocol):
    """Protocol for asynchronous aspect implementations."""

    async def before_async(self, *args: Any, **kwargs: Any) -> None:
        """Execute before the target async method is called.

        Args:
            *args: Positional arguments for the target method.
            **kwargs: Keyword arguments for the target method.
        """
        return

    async def after_raising_async(self, error: Exception) -> None:
        """Execute after the target async method raises an exception.

        Args:
            error: The exception that was raised.
        """
        return

    async def after_returning_async(self, result: Any) -> None:
        """Execute after the target async method returns successfully.

        Args:
            result: The return value from the target method.
        """
        return

    async def after_async(self) -> None:
        """Execute after the target async method completes (regardless of outcome)."""
        return

    async def around_async(
        self,
        joinpoint: AsyncFunc,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Wrap around the target async method execution.

        Args:
            joinpoint: The target async method to be executed.
            *args: Positional arguments for the target method.
            **kwargs: Keyword arguments for the target method.

        Returns:
            The result of the joinpoint execution.
        """
        return await joinpoint(*args, **kwargs)


AspectT = TypeVar("AspectT", bound=type[IAspect])
AsyncAspectT = TypeVar("AsyncAspectT", bound=type[IAsyncAspect])
