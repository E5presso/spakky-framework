"""Binding policy values for dependency injection candidate selection."""

from spakky.core.common.mutability import immutable


@immutable
class PodBinding:
    """Explicit interface-to-implementation binding policy.

    Application or feature configuration can register this value with
    ApplicationContext to select one implementation when multiple Pods provide
    the same interface.
    """

    interface: type
    """Requested interface or port type."""

    implementation_type: type | None = None
    """Concrete implementation type to select."""

    implementation_name: str | None = None
    """Registered Pod name to select."""
