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

    def __init__(self, dependency_chain: list[type]) -> None:
        """Initialize with dependency chain for detailed error message.

        Args:
            dependency_chain: List of types showing the circular dependency path.
        """
        chain = " -> ".join(t.__name__ for t in dependency_chain)
        super().__init__(f"Circular dependency detected: {chain}")
        self.dependency_chain = dependency_chain


class NoSuchPodError(AbstractSpakkyPodError):
    """Raised when requested Pod cannot be found in container."""

    def __init__(self, type_: type, name: str | None = None) -> None:
        """Initialize with search criteria for detailed error message.

        Args:
            type_: The type that was searched for.
            name: Optional name qualifier that was used.
        """
        message: str = f"No Pod found for type '{type_.__name__}'"
        if name:
            message += f" with name '{name}'"
        super().__init__(message)
        self.type_ = type_
        self.name = name


class NoUniquePodError(AbstractSpakkyPodError):
    """Raised when multiple Pods match criteria without clear qualification."""

    def __init__(self, type_: type, candidates: list[str]) -> None:
        """Initialize with conflicting candidates for detailed error message.

        Args:
            type_: The type that had multiple matches.
            candidates: List of Pod names that matched.
        """
        pod_list = ", ".join(f"'{c}'" for c in candidates)
        message: str = (
            f"Multiple Pods found for type '{type_.__name__}': {pod_list}. "
            f"Use @Primary or provide a name/qualifier to disambiguate."
        )
        super().__init__(message)
        self.type_ = type_
        self.candidates = candidates


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
