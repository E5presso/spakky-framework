"""Structured diagnostics for Pod dependency resolution."""

from spakky.core.common.mutability import immutable


@immutable
class PodDependencyPathNode:
    """One Pod dependency graph edge observed during resolution."""

    pod_name: str
    """Registered Pod name for the node being instantiated."""

    pod_type_name: str
    """Registered Pod type name for the node being instantiated."""

    dependency_parameter_name: str | None = None
    """Constructor or factory parameter that requested the next dependency."""

    requested_type_name: str | None = None
    """Requested dependency type name for this graph edge."""


@immutable
class PodDependencyResolutionDiagnostic:
    """Structured dependency resolution failure details."""

    failed_pod_name: str
    """Registered Pod name where resolution failed."""

    failed_pod_type_name: str
    """Registered Pod type name where resolution failed."""

    dependency_parameter_name: str | None
    """Dependency parameter that could not be resolved, when applicable."""

    requested_type_name: str | None
    """Requested dependency type name that failed, when applicable."""

    path: tuple[PodDependencyPathNode, ...]
    """Dependency path from the root Pod to the failure point."""

    def as_detail_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return stable key/value details for report adapters."""
        path_value = " -> ".join(
            node.pod_type_name
            if node.dependency_parameter_name is None
            else (
                f"{node.pod_type_name}.{node.dependency_parameter_name}"
                f":{node.requested_type_name}"
            )
            for node in self.path
        )
        details = (
            ("failed_pod", self.failed_pod_name),
            ("failed_pod_type", self.failed_pod_type_name),
            ("dependency_path", path_value),
        )
        if self.dependency_parameter_name is None:
            return details
        return details + (
            ("dependency_parameter", self.dependency_parameter_name),
            ("requested_type", self.requested_type_name or ""),
        )
