"""spakky-auth provider integration tests."""

from spakky.auth import (
    AuthCapability,
    AuthorizationDecisionState,
    AuthorizationRequest,
    PermissionCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
)
from spakky.plugins.policy.auth_provider import (
    POLICY_AUTH_PROVIDER_ID,
    SpakkyPolicyAuthProvider,
    policy_auth_provider_contribution,
)


def test_policy_auth_provider_exposes_auth_capabilities():
    """Contribution advertises policy evaluation auth capabilities."""
    contribution = policy_auth_provider_contribution()
    assert contribution.provider_id == POLICY_AUTH_PROVIDER_ID
    assert contribution.supports(AuthCapability.POLICY_EVALUATION)
    assert contribution.supports(AuthCapability.PERMISSION_CHECK)
    assert contribution.supports(AuthCapability.ROLE_CHECK)
    assert contribution.supports(AuthCapability.SCOPE_CHECK)
    assert not contribution.supports(AuthCapability.PASSWORD_HASH)


def test_policy_auth_provider_delegates_checks(policy_document, auth_context):
    """Provider implements the public auth checker ports."""
    provider = SpakkyPolicyAuthProvider(policy_document)
    assert (
        provider.evaluate_policy(
            AuthorizationRequest(
                auth_context=auth_context,
                resource="article:1",
                action="article:read",
                tenant="tenant:acme",
            )
        ).state
        is AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_permission(
            PermissionCheckRequest(
                auth_context=auth_context,
                permission="permission:article-read",
                resource="article:1",
                tenant="tenant:acme",
            )
        ).state
        is AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_role(
            RoleCheckRequest(
                auth_context=auth_context, role="role:editor", tenant="tenant:acme"
            )
        ).state
        is AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_scope(
            ScopeCheckRequest(auth_context=auth_context, scope="scope:articles")
        ).state
        is AuthorizationDecisionState.ALLOW
    )
