"""Protocol for Pod post-processors.

This module defines the IPostProcessor protocol for transforming
Pod instances after creation but before use.
"""

from abc import abstractmethod
from typing import Protocol, runtime_checkable


@runtime_checkable
class IPostProcessor(Protocol):
    """Protocol for processing Pods after instantiation.

    Post-processors can wrap, modify, or enhance Pod instances.
    Common uses include AOP proxy creation, dependency injection,
    and lifecycle management.
    """

    @abstractmethod
    def post_process(self, pod: object) -> object:
        """Process a Pod instance.

        Args:
            pod: The Pod instance to process.

        Returns:
            The processed Pod instance (may be wrapped or modified).
        """
        ...
