"""Protocol and errors for Pod container interface.

This module defines the IContainer protocol for managing Pod lifecycle
and dependency injection.
"""

from abc import abstractmethod
from typing import Callable, Protocol, overload, runtime_checkable
from uuid import UUID

from spakky.core.types import ObjectT
from spakky.pod.annotations.pod import Pod, PodType
from spakky.pod.error import AbstractSpakkyPodError


class CircularDependencyGraphDetectedError(AbstractSpakkyPodError):
    """Raised when circular dependency is detected during Pod instantiation."""

    message = "Circular dependency graph detected"


class NoSuchPodError(AbstractSpakkyPodError):
    """Raised when requested Pod cannot be found in container."""

    message = "No such pod found in container"


class NoUniquePodError(AbstractSpakkyPodError):
    """Raised when multiple Pods match criteria without clear qualification."""

    message = "No unique pod found; multiple candidates exist"


class CannotRegisterNonPodObjectError(AbstractSpakkyPodError):
    """Raised when attempting to register object without @Pod annotation."""

    message = "Cannot register a non-pod object"


class PodNameAlreadyExistsError(AbstractSpakkyPodError):
    """Raised when Pod name conflicts with existing registration."""

    message = "Pod name already exists"


@runtime_checkable
class IContainer(Protocol):
    """Protocol for IoC container managing Pod instances."""

    @property
    @abstractmethod
    def pods(self) -> dict[str, Pod]:
        """Get all registered Pods.

        Returns:
            Dictionary mapping Pod names to Pod metadata.
        """
        ...

    @abstractmethod
    def add(self, obj: PodType) -> None:
        """Register a Pod in the container.

        Args:
            obj: The Pod-annotated class or function to register.
        """
        ...

    @overload
    @abstractmethod
    def get(self, type_: type[ObjectT]) -> ObjectT: ...

    @overload
    @abstractmethod
    def get(self, type_: type[ObjectT], name: str) -> ObjectT: ...

    @abstractmethod
    def get(
        self,
        type_: type[ObjectT],
        name: str | None = None,
    ) -> ObjectT | object:
        """Get a Pod instance by type and optional name.

        Args:
            type_: The type to retrieve.
            name: Optional name qualifier.

        Returns:
            The Pod instance.
        """
        ...

    @overload
    @abstractmethod
    def contains(self, type_: type) -> bool: ...

    @overload
    @abstractmethod
    def contains(self, type_: type, name: str) -> bool: ...

    @abstractmethod
    def contains(
        self,
        type_: type,
        name: str | None = None,
    ) -> bool:
        """Check if a Pod is registered.

        Args:
            type_: The type to check.
            name: Optional name qualifier.

        Returns:
            True if matching Pod exists.
        """
        ...

    @abstractmethod
    def find(self, selector: Callable[[Pod], bool]) -> set[object]:
        """Find all Pod instances matching selector predicate.

        Args:
            selector: Predicate function to filter Pods.

        Returns:
            Set of matching Pod instances.
        """
        ...

    @abstractmethod
    def get_context_id(self) -> UUID:
        """Get unique ID for current context.

        Returns:
            UUID for this context.
        """
        ...

    @abstractmethod
    def clear_context(self) -> None:
        """Clear context-scoped cache for current context."""
        ...
