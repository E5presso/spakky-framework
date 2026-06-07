"""Auth feature contribution for the OpenFGA provider."""

from spakky.core.application.application import SpakkyApplication
from spakky.plugins.openfga.provider import openfga_auth_provider_contribution


def initialize(app: SpakkyApplication) -> None:
    """Register OpenFGA auth capability metadata."""
    app.add(openfga_auth_provider_contribution)
