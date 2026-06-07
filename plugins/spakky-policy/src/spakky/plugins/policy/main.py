"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.policy.auth_provider import SpakkyPolicyAuthProvider


def initialize(app: SpakkyApplication) -> None:
    """Initialize the plugin."""
    app.add(SpakkyPolicyAuthProvider)
