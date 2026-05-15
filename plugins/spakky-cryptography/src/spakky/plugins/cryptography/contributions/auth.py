"""Auth feature contribution for the cryptography provider."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.cryptography.auth_provider import (
    cryptography_auth_provider_contribution,
)


def initialize(app: SpakkyApplication) -> None:
    """Register cryptography auth capability metadata."""
    app.add(cryptography_auth_provider_contribution)
