"""Asyncio utilities for Typer CLI integration.

Provides utilities for running async functions in synchronous contexts,
enabling async command handlers in Typer CLI applications.
"""

import asyncio
from functools import wraps
from typing import Awaitable, Callable

from spakky.core.types import P, R


def run_async(func: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    """Convert an async function to a synchronous function.

    Wraps an async function so it can be called synchronously by running
    it in an asyncio event loop. Useful for CLI commands that need to
    perform async operations.

    Args:
        func: The async function to wrap.

    Returns:
        A synchronous wrapper function that runs the async function.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async def coroutine_wrapper() -> R:
            return await func(*args, **kwargs)

        return asyncio.run(coroutine_wrapper())

    return wrapper
