"""Query pattern abstractions for CQRS.

This module provides base classes and protocols for implementing
query use cases in CQRS architecture.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, TypeVar, runtime_checkable

from spakky.core.mutability import immutable


@immutable
class AbstractQuery(ABC):
    """Base class for query DTOs.

    Queries represent intent to read system state without modification.
    """

    ...


QueryT_contra = TypeVar("QueryT_contra", bound=AbstractQuery, contravariant=True)
"""Contravariant type variable for query types."""

ResultT_co = TypeVar("ResultT_co", bound=Any, covariant=True)
"""Covariant type variable for result types."""


@runtime_checkable
class IQueryUseCase(Protocol[QueryT_contra, ResultT_co]):
    """Protocol for synchronous query use cases."""

    @abstractmethod
    def execute(self, query: QueryT_contra) -> ResultT_co:
        """Execute query and return result.

        Args:
            query: The query to execute.

        Returns:
            Query result.
        """
        ...


@runtime_checkable
class IAsyncQueryUseCase(Protocol[QueryT_contra, ResultT_co]):
    """Protocol for asynchronous query use cases."""

    @abstractmethod
    async def execute(  # pyrefly: ignore
        self, query: QueryT_contra
    ) -> ResultT_co:
        """Execute query asynchronously and return result.

        Args:
            query: The query to execute.

        Returns:
            Query result.
        """
        ...
