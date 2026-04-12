"""Query pattern abstractions for CQRS.

This module provides base classes and protocols for implementing
query use cases in CQRS architecture.
"""

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Generic, TypeVar

from spakky.core.common.mutability import immutable


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


class IQueryUseCase(ABC, Generic[QueryT_contra, ResultT_co]):
    """Protocol for synchronous query use cases."""

    @abstractmethod
    def run(self, query: QueryT_contra) -> ResultT_co:
        """Execute query and return result.

        Args:
            query: The query to execute.

        Returns:
            Query result.
        """
        ...


class IAsyncQueryUseCase(ABC, Generic[QueryT_contra, ResultT_co]):
    """Protocol for asynchronous query use cases."""

    @abstractmethod
    def run(self, query: QueryT_contra) -> Awaitable[ResultT_co]:
        """Execute query asynchronously and return result.

        The declaration uses ``Awaitable[ResultT_co]`` instead of
        ``async def`` so that the covariant ``ResultT_co`` remains sound
        under pyrefly's variance analysis. Concrete implementations may
        still use ``async def run`` because ``Coroutine`` is a subtype of
        ``Awaitable``.

        Args:
            query: The query to execute.

        Returns:
            Awaitable resolving to the query result.
        """
        ...
