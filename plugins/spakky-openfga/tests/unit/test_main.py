from spakky.auth import (
    AuthProviderContribution,
    IAuthorizationPolicyEvaluator,
    IRelationChecker,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.openfga.client import IOpenFgaCheckClient, OpenFgaSdkCheckClient
from spakky.plugins.openfga.config import OpenFgaConfig
from spakky.plugins.openfga.contributions.auth import initialize as initialize_auth
from spakky.plugins.openfga.main import initialize
from spakky.plugins.openfga.provider import OpenFgaAuthProvider


def test_initialize_registers_openfga_auth_provider_bindings() -> None:
    app = SpakkyApplication(ApplicationContext())

    initialize(app)

    assert app.container.contains(OpenFgaConfig)
    assert app.container.contains(OpenFgaSdkCheckClient)
    assert app.container.contains(OpenFgaAuthProvider)
    app.start()
    assert isinstance(app.container.get(IOpenFgaCheckClient), OpenFgaSdkCheckClient)
    assert isinstance(app.container.get(IRelationChecker), OpenFgaAuthProvider)
    assert isinstance(
        app.container.get(IAuthorizationPolicyEvaluator),
        OpenFgaAuthProvider,
    )


def test_auth_contribution_initialize_registers_contribution_pod() -> None:
    app = SpakkyApplication(ApplicationContext())

    initialize_auth(app)

    app.start()
    assert isinstance(
        app.container.get(AuthProviderContribution), AuthProviderContribution
    )
