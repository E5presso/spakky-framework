"""Policy evaluator tests."""

from spakky.auth import (
    AuthContext,
    AuthSubject,
    AuthorizationDecisionState,
    AuthorizationRequest,
    PermissionCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
)
from spakky.plugins.policy.evaluator import (
    PolicyDocumentEvaluator,
    PolicyEvaluationInput,
)
from spakky.plugins.policy.loader import policy_document_from_mapping
from spakky.plugins.policy.model import PolicyEffect, PolicyEvidenceKind


def test_evaluate_allows_rbac_pbac_abac_resource_action_request(
    policy_document, auth_context
):
    """RBAC/PBAC/ABAC inputs can jointly allow a request."""
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(
            auth_context=auth_context,
            resource="article:1",
            action="article:read",
            tenant="tenant:acme",
            policy="policy:article-read",
        )
    )
    assert result.allowed is True
    assert result.effect is PolicyEffect.ALLOW
    assert PolicyEvidenceKind.CONDITION_MATCHED in {
        item.kind for item in result.evidence
    }


def test_evaluate_deny_takes_precedence_over_allow(policy_document, auth_context):
    """Explicit deny wins even when an allow statement matched first."""
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(
            auth_context=auth_context,
            resource="mail:1",
            policy="policy:deny-email",
        )
    )
    assert result.allowed is False
    assert result.effect is PolicyEffect.DENY
    assert result.evidence[-1].statement == "deny-email-domain"


def test_evaluate_default_denies_when_no_statement_matches(
    policy_document, auth_context
):
    """No matching allow statement produces default deny evidence."""
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(
            auth_context=auth_context,
            resource="article:2",
            action="article:read",
            policy="policy:article-read",
        )
    )
    assert result.allowed is False
    assert result.effect is None
    assert result.evidence[-1].kind is PolicyEvidenceKind.DEFAULT_DENY


def test_evaluate_named_policy_uses_any_or_not_composition(
    policy_document, auth_context
):
    """Named policy statements expose OR/ANY user DX."""
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(auth_context=auth_context, policy="policy:composed")
    )
    assert result.allowed is True


def test_evaluate_unknown_named_policy_defaults_to_deny(policy_document, auth_context):
    """Unknown named policy references do not silently allow."""
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(auth_context=auth_context, policy="policy:missing")
    )
    assert result.allowed is False
    assert result.evidence == (result.evidence[0],)
    assert result.evidence[0].kind is PolicyEvidenceKind.DEFAULT_DENY


def test_evaluate_authorization_returns_auth_decision(policy_document, auth_context):
    """Provider-neutral AuthorizationRequest maps to AuthorizationDecision."""
    decision = PolicyDocumentEvaluator(policy_document).evaluate_authorization(
        AuthorizationRequest(
            auth_context=auth_context,
            resource="article:1",
            action="article:read",
            tenant="tenant:acme",
        )
    )
    assert decision.state is AuthorizationDecisionState.ALLOW


def test_evaluate_authorization_denies_when_tenant_is_missing(
    policy_document, auth_context
):
    """Tenant-scoped statements do not match missing tenant refs."""
    tenantless_context = AuthContext(
        subject=auth_context.subject,
        issuer=auth_context.issuer,
        roles=auth_context.roles,
        scopes=auth_context.scopes,
        claims=auth_context.claims,
    )
    decision = PolicyDocumentEvaluator(policy_document).evaluate_authorization(
        AuthorizationRequest(
            auth_context=tenantless_context,
            resource="article:1",
            action="article:read",
        )
    )
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(
            auth_context=tenantless_context,
            resource="article:1",
            action="article:read",
            policy="policy:article-read",
        )
    )
    assert decision.state is AuthorizationDecisionState.ALLOW
    assert result.allowed is False


def test_check_permission_uses_role_scope_and_subject_expansions(
    policy_document, auth_context
):
    """Permission checks expand roles, scopes, and document subject grants."""
    evaluator = PolicyDocumentEvaluator(policy_document)
    article_decision = evaluator.check_permission(
        PermissionCheckRequest(
            auth_context=auth_context,
            permission="permission:article-read",
            resource="article:1",
            tenant="tenant:acme",
        )
    )
    direct_decision = evaluator.check_permission(
        PermissionCheckRequest(
            auth_context=auth_context,
            permission="permission:direct",
            tenant="tenant:acme",
        )
    )
    assert article_decision.state is AuthorizationDecisionState.ALLOW
    assert direct_decision.state is AuthorizationDecisionState.ALLOW


def test_check_permission_denies_missing_subject_permission(
    policy_document, auth_context
):
    """Permission checks do not grant the requested permission by echoing it."""
    decision = PolicyDocumentEvaluator(policy_document).check_permission(
        PermissionCheckRequest(
            auth_context=auth_context,
            permission="permission:missing",
            tenant="tenant:acme",
        )
    )
    assert decision.state is AuthorizationDecisionState.DENY


def test_check_role_and_scope_use_canonical_refs(policy_document, auth_context):
    """Role and scope checks use canonical refs from the auth context and document."""
    evaluator = PolicyDocumentEvaluator(policy_document)
    role_decision = evaluator.check_role(
        RoleCheckRequest(
            auth_context=auth_context, role="role:editor", tenant="tenant:acme"
        )
    )
    scope_decision = evaluator.check_scope(
        ScopeCheckRequest(auth_context=auth_context, scope="scope:reports")
    )
    assert role_decision.state is AuthorizationDecisionState.ALLOW
    assert scope_decision.state is AuthorizationDecisionState.ALLOW


def test_subject_absence_uses_auth_context_roles(policy_document, auth_context):
    """Unknown document subjects still evaluate AuthContext role and scope refs."""
    unknown_context = AuthContext(
        subject=AuthSubject(id="user:bob"),
        issuer=auth_context.issuer,
        tenant=auth_context.tenant,
        roles=auth_context.roles,
        scopes=auth_context.scopes,
        claims=auth_context.claims,
    )
    result = PolicyDocumentEvaluator(policy_document).evaluate(
        PolicyEvaluationInput(
            auth_context=unknown_context,
            resource="article:1",
            action="article:read",
            tenant="tenant:acme",
            policy="policy:article-read",
        )
    )
    assert result.allowed is True


def test_subject_and_scope_specific_statement_matches(auth_context):
    """Subject and scope filters use canonical refs."""
    document = policy_document_from_mapping(
        {
            "version": "1",
            "policies": [
                {
                    "ref": "policy:subject-scope",
                    "statements": [
                        {
                            "ref": "allow-subject-scope",
                            "effect": "allow",
                            "subjects": ["user:alice"],
                            "scopes": ["scope:articles"],
                        }
                    ],
                }
            ],
        }
    )
    result = PolicyDocumentEvaluator(document).evaluate(
        PolicyEvaluationInput(auth_context=auth_context, policy="policy:subject-scope")
    )
    assert result.allowed is True


def test_no_condition_statement_matches(auth_context):
    """Statements without conditions can match directly."""
    document = policy_document_from_mapping(
        {
            "version": "1",
            "policies": [
                {
                    "ref": "policy:no-condition",
                    "statements": [{"ref": "allow", "effect": "allow"}],
                }
            ],
        }
    )
    result = PolicyDocumentEvaluator(document).evaluate(
        PolicyEvaluationInput(auth_context=auth_context, policy="policy:no-condition")
    )
    assert result.allowed is True


def test_missing_named_condition_reference_fails_closed(auth_context):
    """Unknown named condition references do not match."""
    document = policy_document_from_mapping(
        {
            "version": "1",
            "policies": [
                {
                    "ref": "policy:missing-condition",
                    "statements": [
                        {
                            "ref": "allow-missing-condition",
                            "effect": "allow",
                            "condition": "condition:missing",
                        }
                    ],
                }
            ],
        }
    )
    result = PolicyDocumentEvaluator(document).evaluate(
        PolicyEvaluationInput(
            auth_context=auth_context, policy="policy:missing-condition"
        )
    )
    assert result.allowed is False
    assert PolicyEvidenceKind.CONDITION_FAILED in {
        item.kind for item in result.evidence
    }
