"""Plugin initialization entry point."""

from spakky.auth import (
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRoleChecker,
    IScopeChecker,
)
from spakky.core.application.application import SpakkyApplication
from spakky.plugins.policy.auth_provider import (
    SpakkyPolicyAuthProvider,
    spakky_policy_document,
)
from spakky.plugins.policy.config import SpakkyPolicyConfig


def initialize(app: SpakkyApplication) -> None:
    """Register policy config, document, provider, and auth port bindings."""
    app.add(SpakkyPolicyConfig)
    app.add(spakky_policy_document)
    app.add(SpakkyPolicyAuthProvider)
    app.container.bind_to_type(IAuthorizationPolicyEvaluator, SpakkyPolicyAuthProvider)
    app.container.bind_to_type(IPermissionChecker, SpakkyPolicyAuthProvider)
    app.container.bind_to_type(IRoleChecker, SpakkyPolicyAuthProvider)
    app.container.bind_to_type(IScopeChecker, SpakkyPolicyAuthProvider)
