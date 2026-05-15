"""Plugin initialization entry point for spakky-auth."""

from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-auth package.

    The semantic model is exposed as importable provider-neutral contracts.
    Runtime providers, decorators, and enforcement components are added by
    downstream auth issues.
    """
    return
