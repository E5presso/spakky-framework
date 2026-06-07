"""Plugin initialization for the OpenFGA auth provider."""

from spakky.auth import IAuthorizationPolicyEvaluator, IRelationChecker
from spakky.core.application.application import SpakkyApplication

from spakky.plugins.openfga.client import IOpenFgaCheckClient, OpenFgaSdkCheckClient
from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.provider import OpenFgaAuthProvider


def initialize(app: SpakkyApplication) -> None:
    """Register OpenFGA check client and auth provider bindings."""
    app.add(OpenFgaConfig)
    app.add(OpenFgaSdkCheckClient)
    app.add(OpenFgaAuthProvider)
    app.container.bind_to_type(IOpenFgaCheckClient, OpenFgaSdkCheckClient)
    app.container.bind_to_type(IRelationChecker, OpenFgaAuthProvider)
    app.container.bind_to_type(IAuthorizationPolicyEvaluator, OpenFgaAuthProvider)
