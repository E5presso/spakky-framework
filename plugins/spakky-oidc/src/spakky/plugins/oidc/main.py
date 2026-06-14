"""Plugin initialization for OIDC bearer authentication."""

from spakky.auth import IAuthenticationProvider
from spakky.core.application.application import SpakkyApplication
from spakky.plugins.oidc.provider import OidcAuthenticationProvider, OidcProviderConfig


def initialize(app: SpakkyApplication) -> None:
    """Register OIDC configuration and authentication provider binding."""
    app.add(OidcProviderConfig)
    app.add(OidcAuthenticationProvider)
    app.container.bind_to_type(IAuthenticationProvider, OidcAuthenticationProvider)
