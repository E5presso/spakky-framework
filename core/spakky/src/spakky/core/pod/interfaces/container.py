"""Interface and errors for Pod container interface.

This module defines the IContainer protocol for managing Pod lifecycle
and dependency injection.
"""

from abc import ABC, abstractmethod
from typing import overload
from collections.abc import Callable

from spakky.core.common.interfaces.representable import IRepresentable
from spakky.core.pod.annotations.pod import Pod, PodType
from spakky.core.pod.binding import PodBinding
from spakky.core.pod.diagnostics import (
    PodCandidateDiagnostic,
    PodDependencyResolutionDiagnostic,
)
from spakky.core.pod.error import AbstractSpakkyPodError


class CircularDependencyGraphDetectedError(AbstractSpakkyPodError, IRepresentable):
    """Raised when circular dependency is detected during Pod instantiation.

    Attributes:
        dependency_chain: List of types showing the circular dependency path.
    """

    message = "Circular dependency graph detected"
    dependency_chain: list[type]
    dependency_diagnostic: PodDependencyResolutionDiagnostic | None

    def __init__(
        self,
        dependency_chain: list[type],
        dependency_diagnostic: PodDependencyResolutionDiagnostic | None = None,
    ) -> None:
        """Initialize with dependency chain information.

        Args:
            dependency_chain: List of types in dependency order, ending with the duplicate type.
            dependency_diagnostic: Optional structured dependency path details.
        """
        self.dependency_chain = dependency_chain
        self.dependency_diagnostic = dependency_diagnostic
        if not dependency_chain:
            super().__init__(self.message)
            return

        lines = [self.message, "Dependency path:"]
        for i, type_ in enumerate(dependency_chain):
            type_name = (
                type_.__name__
                if hasattr(type_, "__name__")  # diagnostic fallback for typing aliases
                else str(type_)
            )
            indent = "  " * i
            arrow = "└─> " if i > 0 else ""

            if i == len(dependency_chain) - 1:
                lines.append(f"{indent}{arrow}{type_name} (CIRCULAR!)")
            else:
                lines.append(f"{indent}{arrow}{type_name}")

        super().__init__("\n".join(lines))


class NoSuchPodError(AbstractSpakkyPodError):
    """Raised when requested Pod cannot be found in container."""

    message = "No such pod found in container"


class NoUniquePodError(AbstractSpakkyPodError):
    """Raised when multiple Pods match criteria without clear qualification."""

    message = "No unique pod found; multiple candidates exist"
    requested_type: type
    candidates: tuple[PodCandidateDiagnostic, ...]
    dependency_diagnostic: PodDependencyResolutionDiagnostic | None
    resolution_hints: tuple[str, ...]

    def __init__(
        self,
        requested_type: type,
        candidates: tuple[PodCandidateDiagnostic, ...],
        dependency_diagnostic: PodDependencyResolutionDiagnostic | None = None,
        resolution_hints: tuple[str, ...] = (),
    ) -> None:
        """Initialize ambiguity details.

        Args:
            requested_type: Dependency type requested by the caller.
            candidates: Candidate Pods that matched the requested type.
            dependency_diagnostic: Optional structured dependency path.
            resolution_hints: Actions that can make the selection explicit.
        """
        self.requested_type = requested_type
        self.candidates = candidates
        self.dependency_diagnostic = dependency_diagnostic
        self.resolution_hints = resolution_hints
        candidate_names = ", ".join(candidate.pod_name for candidate in candidates)
        super().__init__(
            "\n".join(
                (
                    self.message,
                    "Requested type: " + requested_type.__name__,
                    "Candidates: " + candidate_names,
                    "Resolution: " + "; ".join(resolution_hints),
                )
            )
        )


class InvalidPodBindingError(AbstractSpakkyPodError):
    """Raised when a binding policy does not identify exactly one target kind."""

    message = "Pod binding must specify exactly one implementation target"


class NoSuchPodBindingTargetError(AbstractSpakkyPodError):
    """Raised when an explicit binding does not match any candidate Pod."""

    message = "Pod binding target does not match a registered candidate"

    binding: PodBinding

    def __init__(self, binding: PodBinding) -> None:
        """Initialize binding target details."""
        self.binding = binding
        super().__init__(self.message)


class PodBindingNotSupportedError(AbstractSpakkyPodError):
    """Raised when a container does not implement explicit binding policies."""

    message = "Pod binding policy is not supported by this container"


class CannotRegisterNonPodObjectError(AbstractSpakkyPodError):
    """Raised when attempting to register object without @Pod annotation."""

    message = "Cannot register a non-pod object"


class PodNameAlreadyExistsError(AbstractSpakkyPodError):
    """Raised when Pod name conflicts with existing registration."""

    message = "Pod name already exists"


class IContainer(ABC):
    """Interface for IoC container managing Pod instances."""

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

    def bind(self, binding: PodBinding) -> None:
        """Register an explicit interface-to-implementation binding policy.

        Args:
            binding: Binding value supplied by application or feature config.
        """
        raise PodBindingNotSupportedError

    def bind_to_type(self, interface: type, implementation: type) -> None:
        """Bind an interface to a concrete implementation type."""
        raise PodBindingNotSupportedError

    def bind_to_name(self, interface: type, name: str) -> None:
        """Bind an interface to a registered Pod name."""
        raise PodBindingNotSupportedError

    @overload
    @abstractmethod
    def get[T: object](self, type_: type[T]) -> T: ...

    @overload
    @abstractmethod
    def get[T: object](self, type_: type[T], name: str) -> T: ...

    @abstractmethod
    def get[T: object](
        self,
        type_: type[T],
        name: str | None = None,
    ) -> T | object:
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
    def get_or_none[T: object](self, type_: type[T]) -> T | None: ...

    @overload
    @abstractmethod
    def get_or_none[T: object](self, type_: type[T], name: str) -> T | None: ...

    @abstractmethod
    def get_or_none[T: object](
        self,
        type_: type[T],
        name: str | None = None,
    ) -> T | None:
        """Get a Pod instance by type and optional name, or None if not found.

        Args:
            type_: The type to retrieve.
            name: Optional name qualifier.

        Returns:
            The Pod instance, or None if no matching Pod found.
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
