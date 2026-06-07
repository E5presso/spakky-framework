"""Plugin initialization for cryptography utilities and auth provider."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.cryptography.auth_provider import CryptographyAuthProvider


def initialize(app: SpakkyApplication) -> None:
    """Register the cryptography auth provider."""
    app.add(CryptographyAuthProvider)
