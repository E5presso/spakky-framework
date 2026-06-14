"""spakky-auth provider integration tests."""

from spakky.auth import (
    AuthCapability,
    AuthorizationDecisionState,
    AuthorizationRequest,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRoleChecker,
    IScopeChecker,
    PermissionCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.plugins.policy.config import SpakkyPolicyConfig
from spakky.plugins.policy.main import initialize
from spakky.plugins.policy.model import PolicyDocument
from spakky.plugins.policy.auth_provider import (
    POLICY_AUTH_PROVIDER_ID,
    SpakkyPolicyAuthProvider,
    policy_auth_provider_contribution,
    spakky_policy_document,
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


def test_initialize_expect_registers_policy_provider_bindings():
    """initialize()가 policy provider를 auth port들에 binding하는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    initialize(app)
    app.start()

    assert isinstance(app.container.get(SpakkyPolicyConfig), SpakkyPolicyConfig)
    assert isinstance(app.container.get(PolicyDocument), PolicyDocument)
    assert isinstance(
        app.container.get(IAuthorizationPolicyEvaluator),
        SpakkyPolicyAuthProvider,
    )
    assert isinstance(app.container.get(IPermissionChecker), SpakkyPolicyAuthProvider)
    assert isinstance(app.container.get(IRoleChecker), SpakkyPolicyAuthProvider)
    assert isinstance(app.container.get(IScopeChecker), SpakkyPolicyAuthProvider)


def test_policy_document_pod_expect_loads_configured_document_path(tmp_path):
    """설정된 document_path가 DI policy document로 로드되는지 검증한다."""
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
version: "2026-06"
metadata:
  name: configured-policy
""",
        encoding="UTF-8",
    )
    config = SpakkyPolicyConfig().model_copy(update={"document_path": policy_path})

    document = spakky_policy_document(config)

    assert document.version == "2026-06"
    assert document.metadata.name == "configured-policy"


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
