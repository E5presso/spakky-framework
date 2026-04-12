"""Command pattern abstractions for CQRS.

This module provides base classes and protocols for implementing
command use cases in CQRS architecture.
"""

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Generic, TypeVar

from spakky.core.common.mutability import immutable


@immutable
class AbstractCommand(ABC):
    """Base class for command DTOs.

    Commands represent intent to change system state.
    """

    ...


CommandT_contra = TypeVar("CommandT_contra", bound=AbstractCommand, contravariant=True)
"""Contravariant type variable for command types."""

ResultT_co = TypeVar("ResultT_co", bound=Any, covariant=True)
"""Covariant type variable for result types."""


class ICommandUseCase(ABC, Generic[CommandT_contra, ResultT_co]):
    """Protocol for synchronous command use cases."""

    @abstractmethod
    def run(self, command: CommandT_contra) -> ResultT_co:
        """Execute command and return result.

        Args:
            command: The command to execute.

        Returns:
            Result of command execution.
        """
        ...


class IAsyncCommandUseCase(ABC, Generic[CommandT_contra, ResultT_co]):
    """Protocol for asynchronous command use cases."""

    @abstractmethod
    def run(self, command: CommandT_contra) -> Awaitable[ResultT_co]:
        """Execute command asynchronously and return result.

        The declaration uses ``Awaitable[ResultT_co]`` instead of
        ``async def`` so that the covariant ``ResultT_co`` remains sound
        under pyrefly's variance analysis. Concrete implementations may
        still use ``async def run`` because ``Coroutine`` is a subtype of
        ``Awaitable``.

        Args:
            command: The command to execute.

        Returns:
            Awaitable resolving to the result of command execution.
        """
        ...
