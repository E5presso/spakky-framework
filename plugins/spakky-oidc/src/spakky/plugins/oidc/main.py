"""Plugin initialization for OIDC bearer authentication."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.oidc.provider import OidcAuthenticationProvider


def initialize(app: SpakkyApplication) -> None:
    """Register the OIDC authentication provider."""
    app.add(OidcAuthenticationProvider)
