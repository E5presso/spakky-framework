"""Plugin initialization for the OAuth 2.0 client."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.oauth.client import OAuthClient
from spakky.plugins.oauth.config import OAuthConfig


def initialize(app: SpakkyApplication) -> None:
    """Register the OAuth configuration and client service.

    Token and authorization-state stores are application-owned: register one
    ``IOAuthTokenStore`` and one ``IOAuthAuthorizationStateStore`` Pod.
    """
    app.add(OAuthConfig)
    app.add(OAuthClient)
