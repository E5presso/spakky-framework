"""Command pattern abstractions for CQRS.

This module provides base classes and protocols for implementing
command use cases in CQRS architecture.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

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
    def execute(self, command: CommandT_contra) -> ResultT_co:
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
    async def execute(  # type: ignore
        self, command: CommandT_contra
    ) -> ResultT_co:
        """Execute command asynchronously and return result.

        Args:
            command: The command to execute.

        Returns:
            Result of command execution.
        """
        ...
