"""Auth feature contribution for the policy provider."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.policy.auth_provider import policy_auth_provider_contribution


def initialize(app: SpakkyApplication) -> None:
    """Register policy auth capability metadata."""
    app.add(policy_auth_provider_contribution)
