"""Auth feature contribution for the OIDC provider."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.oidc.provider import oidc_auth_provider_contribution


def initialize(app: SpakkyApplication) -> None:
    """Register OIDC auth capability metadata."""
    app.add(oidc_auth_provider_contribution)
