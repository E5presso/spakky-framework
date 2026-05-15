"""Plugin initialization entry point for spakky-auth."""

from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-auth package.

    This registration ticket intentionally provides no auth semantic model or
    enforcement component. Those contracts are added by downstream auth issues.
    """
    return
