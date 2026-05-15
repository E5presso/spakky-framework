from abc import ABCMeta
from datetime import UTC, datetime, timedelta
from typing import override

from spakky.auth import (
    AUTH_CONTRIBUTION_ENTRY_POINT_GROUP,
    AuthCapability,
    AuthContext,
    AuthContextSnapshot,
    AuthContextSnapshotSignature,
    AuthDynamicRef,
    AuthDynamicRefKind,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthProviderContribution,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthorizationRequest,
    CredentialCarrier,
    CredentialCarrierKind,
    CredentialCarrierLocation,
    IAuthContextSnapshotSigner,
    IAuthContextSnapshotVerifier,
    IAuthInvocationResolver,
    IAuthenticationProvider,
    IAuthorizationPolicyEvaluator,
    IPasswordHasher,
    IPasswordVerifier,
    IPermissionChecker,
    IRelationChecker,
    IRoleChecker,
    IScopeChecker,
    PermissionCheckRequest,
    RelationCheckRequest,
    ResolvedAuthReference,
    RoleCheckRequest,
    ScopeCheckRequest,
    SnapshotSignRequest,
)


def test_auth_capability_enum_covers_provider_neutral_capabilities() -> None:
    assert {capability.value for capability in AuthCapability} == {
        "AUTHENTICATION",
        "POLICY_EVALUATION",
        "PERMISSION_CHECK",
        "ROLE_CHECK",
        "SCOPE_CHECK",
        "RELATION_CHECK",
        "SNAPSHOT_SIGN",
        "SNAPSHOT_VERIFY",
        "PASSWORD_HASH",
        "PASSWORD_VERIFY",
    }


def test_auth_contribution_declares_feature_local_capability_set() -> None:
    contribution = AuthProviderContribution(
        provider_id="provider:fake",
        capabilities=frozenset(
            {
                AuthCapability.AUTHENTICATION,
                AuthCapability.POLICY_EVALUATION,
            }
        ),
    )

    assert AUTH_CONTRIBUTION_ENTRY_POINT_GROUP == "spakky.contributions.spakky.auth"
    assert contribution.provider_id == "provider:fake"
    assert contribution.supports(AuthCapability.AUTHENTICATION)
    assert not contribution.supports(AuthCapability.PASSWORD_HASH)


def test_public_auth_ports_are_abc_contracts() -> None:
    ports = (
        IAuthenticationProvider,
        IAuthorizationPolicyEvaluator,
        IPermissionChecker,
        IRoleChecker,
        IScopeChecker,
        IRelationChecker,
        IAuthContextSnapshotSigner,
        IAuthContextSnapshotVerifier,
        IPasswordHasher,
        IPasswordVerifier,
        IAuthInvocationResolver,
    )

    for port in ports:
        assert isinstance(port, ABCMeta)
        assert len(port.__abstractmethods__) > 0


def test_fake_provider_implements_all_auth_contracts() -> None:
    auth_context = AuthContext(
        subject=AuthSubject(id="subject-1"),
        issuer="issuer-1",
        tenant="tenant-1",
        roles=("role:admin",),
        scopes=("documents:read",),
    )
    invocation = AuthInvocation(
        boundary="http",
        operation="documents.read",
        subject=auth_context.subject,
        attributes=(AuthInvocationAttribute(name="document_id", value="doc-1"),),
    )

    class FakeAuthProvider(
        IAuthenticationProvider,
        IAuthorizationPolicyEvaluator,
        IPermissionChecker,
        IRoleChecker,
        IScopeChecker,
        IRelationChecker,
        IAuthContextSnapshotSigner,
        IAuthContextSnapshotVerifier,
        IPasswordHasher,
        IPasswordVerifier,
        IAuthInvocationResolver,
    ):
        @override
        def authenticate(
            self,
            credential: CredentialCarrier,
            invocation: AuthInvocation,
        ) -> AuthContext:
            return AuthContext(
                subject=AuthSubject(id=credential.material),
                issuer=invocation.boundary,
            )

        @override
        def evaluate_policy(
            self,
            request: AuthorizationRequest,
        ) -> AuthorizationDecision:
            if request.resource == "document:doc-1" and request.action == "read":
                return AuthorizationDecision.allow()
            return AuthorizationDecision.deny(AuthorizationReasonCode.POLICY_DENIED)

        @override
        def check_permission(
            self,
            request: PermissionCheckRequest,
        ) -> AuthorizationDecision:
            if request.permission == "documents:read":
                return AuthorizationDecision.allow()
            return AuthorizationDecision.deny(
                AuthorizationReasonCode.INSUFFICIENT_SCOPE
            )

        @override
        def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
            if request.role in request.auth_context.roles:
                return AuthorizationDecision.allow()
            return AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_ROLE)

        @override
        def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
            if request.scope in request.auth_context.scopes:
                return AuthorizationDecision.allow()
            return AuthorizationDecision.deny(
                AuthorizationReasonCode.INSUFFICIENT_SCOPE
            )

        @override
        def check_relation(
            self,
            request: RelationCheckRequest,
        ) -> AuthorizationDecision:
            if request.relation == "owner" and request.resource == "document:doc-1":
                return AuthorizationDecision.allow()
            return AuthorizationDecision.deny(AuthorizationReasonCode.POLICY_DENIED)

        @override
        def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
            issued_at = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
            return AuthContextSnapshot(
                subject=request.auth_context.subject,
                issuer=request.auth_context.issuer,
                tenant=request.tenant,
                roles=request.auth_context.roles,
                scopes=request.auth_context.scopes,
                issued_at=issued_at,
                expires_at=issued_at + timedelta(minutes=5),
                signature=AuthContextSnapshotSignature(
                    key_id="key-1",
                    algorithm="fake-signature",
                    signature="signed",
                ),
            )

        @override
        def verify_snapshot(
            self,
            snapshot_envelope: str,
            invocation: AuthInvocation,
        ) -> AuthContext:
            return AuthContext(
                subject=AuthSubject(id=snapshot_envelope),
                issuer="issuer-1",
                tenant="tenant-1",
                roles=("role:admin",),
                scopes=("documents:read",),
            )

        @override
        def hash_password(self, password: str) -> str:
            return f"hashed:{password}"

        @override
        def verify_password(
            self,
            password: str,
            password_hash: str,
        ) -> AuthorizationDecision:
            if password_hash == f"hashed:{password}":
                return AuthorizationDecision.allow()
            return AuthorizationDecision.deny(
                AuthorizationReasonCode.INVALID_CREDENTIAL
            )

        @override
        def resolve_ref(
            self,
            invocation: AuthInvocation,
            dynamic_ref: AuthDynamicRef,
        ) -> ResolvedAuthReference:
            return ResolvedAuthReference(
                kind=dynamic_ref.kind,
                value=f"{invocation.operation}:{dynamic_ref.expression}",
            )

    provider = FakeAuthProvider()
    credential = CredentialCarrier(
        kind=CredentialCarrierKind.BEARER_TOKEN,
        location=CredentialCarrierLocation.AUTHORIZATION_HEADER,
        material="subject-1",
    )

    assert provider.authenticate(credential, invocation).subject.id == "subject-1"
    assert (
        provider.evaluate_policy(
            AuthorizationRequest(
                auth_context=auth_context,
                resource="document:doc-1",
                action="read",
                tenant="tenant-1",
            )
        ).state
        == AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.evaluate_policy(
            AuthorizationRequest(
                auth_context=auth_context,
                resource="document:doc-2",
                action="write",
            )
        ).state
        == AuthorizationDecisionState.DENY
    )
    assert (
        provider.check_permission(
            PermissionCheckRequest(
                auth_context=auth_context,
                permission="documents:read",
                resource="document:doc-1",
                tenant="tenant-1",
            )
        ).state
        == AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_permission(
            PermissionCheckRequest(
                auth_context=auth_context,
                permission="documents:delete",
            )
        ).state
        == AuthorizationDecisionState.DENY
    )
    assert (
        provider.check_role(
            RoleCheckRequest(auth_context=auth_context, role="role:admin")
        ).state
        == AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_role(
            RoleCheckRequest(
                auth_context=auth_context,
                role="role:viewer",
                tenant="tenant-1",
            )
        ).state
        == AuthorizationDecisionState.DENY
    )
    assert (
        provider.check_scope(
            ScopeCheckRequest(auth_context=auth_context, scope="documents:read")
        ).state
        == AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_scope(
            ScopeCheckRequest(auth_context=auth_context, scope="documents:write")
        ).state
        == AuthorizationDecisionState.DENY
    )
    assert (
        provider.check_relation(
            RelationCheckRequest(
                auth_context=auth_context,
                relation="owner",
                resource="document:doc-1",
                tenant="tenant-1",
            )
        ).state
        == AuthorizationDecisionState.ALLOW
    )
    assert (
        provider.check_relation(
            RelationCheckRequest(
                auth_context=auth_context,
                relation="viewer",
                resource="document:doc-2",
            )
        ).state
        == AuthorizationDecisionState.DENY
    )
    snapshot = provider.sign_snapshot(
        SnapshotSignRequest(auth_context=auth_context, tenant="tenant-1")
    )
    assert snapshot.tenant == "tenant-1"
    assert provider.verify_snapshot("subject-1", invocation) == auth_context
    assert provider.hash_password("pw") == "hashed:pw"
    assert provider.verify_password("pw", "hashed:pw").state == (
        AuthorizationDecisionState.ALLOW
    )
    assert provider.verify_password("pw", "different").state == (
        AuthorizationDecisionState.DENY
    )
    assert provider.resolve_ref(
        invocation,
        AuthDynamicRef(kind=AuthDynamicRefKind.RESOURCE, expression="document_id"),
    ) == ResolvedAuthReference(
        kind=AuthDynamicRefKind.RESOURCE,
        value="documents.read:document_id",
    )
    assert provider.resolve_ref(
        invocation,
        AuthDynamicRef(kind=AuthDynamicRefKind.ACTION, expression="operation"),
    ) == ResolvedAuthReference(
        kind=AuthDynamicRefKind.ACTION,
        value="documents.read:operation",
    )
    assert provider.resolve_ref(
        invocation,
        AuthDynamicRef(kind=AuthDynamicRefKind.TENANT, expression="tenant"),
    ) == ResolvedAuthReference(
        kind=AuthDynamicRefKind.TENANT,
        value="documents.read:tenant",
    )
