"""Auth provider integration for policy document evaluation."""

from typing import override

from spakky.auth import (
    AuthCapability,
    AuthProviderContribution,
    AuthorizationDecision,
    AuthorizationRequest,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRoleChecker,
    IScopeChecker,
    PermissionCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
)
from spakky.core.pod.annotations.pod import Pod
from spakky.plugins.policy.config import SpakkyPolicyConfig
from spakky.plugins.policy.evaluator import PolicyDocumentEvaluator
from spakky.plugins.policy.loader import (
    load_policy_document,
    policy_document_from_mapping,
)
from spakky.plugins.policy.model import PolicyDocument

POLICY_AUTH_PROVIDER_ID = "provider:spakky-policy"
"""Stable auth provider id advertised by spakky-policy."""


@Pod()
class SpakkyPolicyAuthProvider(
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRoleChecker,
    IScopeChecker,
):
    """Auth capability provider backed by a canonical policy document."""

    _evaluator: PolicyDocumentEvaluator

    def __init__(self, document: PolicyDocument) -> None:
        self._evaluator = PolicyDocumentEvaluator(document)

    @override
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        """Evaluate a resource/action authorization request."""
        return self._evaluator.evaluate_authorization(request)

    @override
    def check_permission(
        self,
        request: PermissionCheckRequest,
    ) -> AuthorizationDecision:
        """Check whether the subject has a permission."""
        return self._evaluator.check_permission(request)

    @override
    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        """Check whether the subject has a role."""
        return self._evaluator.check_role(request)

    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        """Check whether the subject has a scope."""
        return self._evaluator.check_scope(request)


@Pod(name="spakky_policy_document")
def spakky_policy_document(config: SpakkyPolicyConfig) -> PolicyDocument:
    """Load the configured policy document for DI-managed auth providers."""
    if config.document_path is None:
        return policy_document_from_mapping(
            {
                "version": "1",
                "metadata": {"name": "spakky-policy"},
            }
        )
    return load_policy_document(config.document_path)


@Pod(name="spakky_policy_auth_provider_contribution")
def policy_auth_provider_contribution() -> AuthProviderContribution:
    """Return the auth capabilities contributed by spakky-policy."""
    return AuthProviderContribution(
        provider_id=POLICY_AUTH_PROVIDER_ID,
        capabilities=frozenset(
            {
                AuthCapability.POLICY_EVALUATION,
                AuthCapability.PERMISSION_CHECK,
                AuthCapability.ROLE_CHECK,
                AuthCapability.SCOPE_CHECK,
            }
        ),
    )
