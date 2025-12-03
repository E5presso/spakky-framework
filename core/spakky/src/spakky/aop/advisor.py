"""Advisor classes that coordinate aspect execution around method calls.

Advisors wrap methods with aspect logic, executing before/around/after advice
in the correct order and handling exceptions appropriately.
"""

from typing import Any

from spakky.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.types import AsyncFunc, Func


class Advisor:
    """Advisor for synchronous methods with aspect interception."""

    instance: IAspect
    """The aspect instance that provides advice."""

    next: Func
    """The next function in the advice chain."""

    def __init__(self, instance: IAspect, next: Func) -> None:
        """Initialize the advisor.

        Args:
            instance: The aspect instance providing advice.
            next: The next function to call in the chain.
        """
        self.instance = instance
        self.next = next

    def __getattr__(self, name: str) -> Any:
        return getattr(self.next, name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the advised method with aspect logic.

        Coordinates the execution of before, around, after_returning, after_raising,
        and after advice in the correct order.

        Args:
            *args: Positional arguments for the method.
            **kwargs: Keyword arguments for the method.

        Returns:
            Any: The result of the method call.

        Raises:
            Exception: Any exception raised by the advised method or aspect.
        """
        self.instance.before(*args, **kwargs)
        try:
            result = self.instance.around(self.next, *args, **kwargs)
            self.instance.after_returning(result)
            return result
        except Exception as e:
            self.instance.after_raising(e)
            raise
        finally:
            self.instance.after()


class AsyncAdvisor:
    """Advisor for asynchronous methods with aspect interception."""

    instance: IAsyncAspect
    """The async aspect instance that provides advice."""

    next: AsyncFunc
    """The next async function in the advice chain."""

    def __init__(self, instance: IAsyncAspect, next: AsyncFunc) -> None:
        """Initialize the async advisor.

        Args:
            instance: The async aspect instance providing advice.
            next: The next async function to call in the chain.
        """
        self.instance = instance
        self.next = next

    def __getattr__(self, name: str) -> Any:
        return getattr(self.next, name)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the advised async method with aspect logic.

        Coordinates the execution of before, around, after_returning, after_raising,
        and after advice in the correct order for async methods.

        Args:
            *args: Positional arguments for the method.
            **kwargs: Keyword arguments for the method.

        Returns:
            Any: The result of the async method call.

        Raises:
            Exception: Any exception raised by the advised method or aspect.
        """
        await self.instance.before_async(*args, **kwargs)
        try:
            result = await self.instance.around_async(self.next, *args, **kwargs)
            await self.instance.after_returning_async(result)
            return result
        except Exception as e:
            await self.instance.after_raising_async(e)
            raise
        finally:
            await self.instance.after_async()
