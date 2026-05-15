from typing import override

import pytest

from spakky.auth import (
    AuthContext,
    AuthContextNotFoundError,
    AuthRequirement,
    AuthRequirementDeniedError,
    AuthRequirementKind,
    AuthRequirementProviderUnavailableError,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationReasonCode,
    AuthorizationRequest,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRelationChecker,
    IRoleChecker,
    IScopeChecker,
    PermissionCheckRequest,
    RelationCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
    protected,
    require_permission,
    require_policy,
    require_relation,
    require_role,
    require_scope,
    store_auth_context,
)
from spakky.auth.aspects.authorization import (
    _matches_async,
    _matches_sync,
    AsyncAuthorizationAspect,
    AuthorizationAspect,
)
from spakky.core.application.application_context import ApplicationContext


class AllowingAuthorizationPolicyEvaluator(IAuthorizationPolicyEvaluator):
    requests: list[AuthorizationRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class AllowingPermissionChecker(IPermissionChecker):
    requests: list[PermissionCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def check_permission(
        self,
        request: PermissionCheckRequest,
    ) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class AllowingRelationChecker(IRelationChecker):
    requests: list[RelationCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def check_relation(self, request: RelationCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class AllowingRoleChecker(IRoleChecker):
    requests: list[RoleCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class ConfigurableScopeChecker(IScopeChecker):
    requests: list[ScopeCheckRequest]
    decision: AuthorizationDecision

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.requests = []
        self.decision = decision

    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return self.decision


def test_sync_authorization_aspect_enforces_all_requirements_from_auth_context() -> (
    None
):
    application_context = _context_with_auth()
    policy_evaluator = AllowingAuthorizationPolicyEvaluator()
    permission_checker = AllowingPermissionChecker()
    relation_checker = AllowingRelationChecker()
    role_checker = AllowingRoleChecker()
    scope_checker = ConfigurableScopeChecker(AuthorizationDecision.allow())
    aspect = AuthorizationAspect(
        application_context,
        authorization_policy_evaluator=policy_evaluator,
        permission_checker=permission_checker,
        relation_checker=relation_checker,
        role_checker=role_checker,
        scope_checker=scope_checker,
    )

    @require_relation("owner", resource="document:1", tenant="tenant:1")
    @require_policy("document:1", "read", tenant="tenant:1")
    @require_permission("documents:read", resource="document:1", tenant="tenant:1")
    @require_role("role:admin", tenant="tenant:1")
    @require_scope("documents:read")
    def boundary() -> str:
        return "ok"

    assert aspect.around(boundary) == "ok"
    assert permission_checker.requests[0].permission == "documents:read"
    assert policy_evaluator.requests[0].resource == "document:1"
    assert relation_checker.requests[0].relation == "owner"
    assert role_checker.requests[0].role == "role:admin"
    assert scope_checker.requests[0].scope == "documents:read"


async def test_async_authorization_aspect_enforces_protected_boundary() -> None:
    application_context = _context_with_auth()
    aspect = AsyncAuthorizationAspect(application_context)

    @require_scope("documents:read")
    async def boundary() -> str:
        return "ok"

    with pytest.raises(AuthRequirementProviderUnavailableError):
        await aspect.around_async(boundary)


async def test_async_authorization_aspect_enforces_all_requirements() -> None:
    application_context = _context_with_auth()
    policy_evaluator = AllowingAuthorizationPolicyEvaluator()
    permission_checker = AllowingPermissionChecker()
    relation_checker = AllowingRelationChecker()
    role_checker = AllowingRoleChecker()
    scope_checker = ConfigurableScopeChecker(AuthorizationDecision.allow())
    aspect = AsyncAuthorizationAspect(
        application_context,
        authorization_policy_evaluator=policy_evaluator,
        permission_checker=permission_checker,
        relation_checker=relation_checker,
        role_checker=role_checker,
        scope_checker=scope_checker,
    )

    @require_relation("owner", resource="document:1", tenant="tenant:1")
    @require_policy("document:1", "read", tenant="tenant:1")
    @require_permission("documents:read", resource="document:1", tenant="tenant:1")
    @require_role("role:admin", tenant="tenant:1")
    @require_scope("documents:read")
    async def boundary() -> str:
        return "ok"

    assert await aspect.around_async(boundary) == "ok"
    assert permission_checker.requests[0].permission == "documents:read"
    assert policy_evaluator.requests[0].action == "read"
    assert relation_checker.requests[0].resource == "document:1"
    assert role_checker.requests[0].tenant == "tenant:1"
    assert scope_checker.requests[0].scope == "documents:read"


def test_authorization_aspect_allows_undecorated_boundary() -> None:
    aspect = AuthorizationAspect(ApplicationContext())

    def boundary() -> str:
        return "ok"

    assert aspect.around(boundary) == "ok"


async def test_async_authorization_aspect_allows_undecorated_boundary() -> None:
    aspect = AsyncAuthorizationAspect(ApplicationContext())

    async def boundary() -> str:
        return "ok"

    assert await aspect.around_async(boundary) == "ok"


def test_protected_boundary_fails_closed_without_auth_context() -> None:
    aspect = AuthorizationAspect(ApplicationContext())

    @require_scope("documents:read")
    def boundary() -> str:
        return "ok"

    with pytest.raises(AuthContextNotFoundError):
        aspect.around(boundary)


def test_protected_boundary_fails_closed_without_injected_application_context() -> None:
    aspect = AuthorizationAspect()

    @protected
    def boundary() -> str:
        return "ok"

    with pytest.raises(AuthContextNotFoundError):
        aspect.around(boundary)


async def test_async_protected_boundary_fails_closed_without_injected_application_context() -> (
    None
):
    aspect = AsyncAuthorizationAspect()

    @protected
    async def boundary() -> str:
        return "ok"

    with pytest.raises(AuthContextNotFoundError):
        await aspect.around_async(boundary)


def test_non_allow_decision_fails_closed_before_joinpoint() -> None:
    application_context = _context_with_auth()
    scope_checker = ConfigurableScopeChecker(
        AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_SCOPE)
    )
    aspect = AuthorizationAspect(application_context, scope_checker=scope_checker)
    called = False

    @require_scope("documents:write")
    def boundary() -> str:
        nonlocal called
        called = True
        return "ok"

    with pytest.raises(AuthRequirementDeniedError):
        aspect.around(boundary)
    assert not called


def test_authenticated_marker_only_requires_auth_context() -> None:
    application_context = _context_with_auth()
    aspect = AuthorizationAspect(application_context)

    @protected
    def boundary() -> str:
        return "ok"

    assert aspect.around(boundary) == "ok"


async def test_async_non_allow_decision_fails_closed_before_joinpoint() -> None:
    application_context = _context_with_auth()
    scope_checker = ConfigurableScopeChecker(
        AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_SCOPE)
    )
    aspect = AsyncAuthorizationAspect(application_context, scope_checker=scope_checker)
    called = False

    @require_scope("documents:write")
    async def boundary() -> str:
        nonlocal called
        called = True
        return "ok"

    with pytest.raises(AuthRequirementDeniedError):
        await aspect.around_async(boundary)
    assert not called


async def test_async_authenticated_marker_only_requires_auth_context() -> None:
    application_context = _context_with_auth()
    aspect = AsyncAuthorizationAspect(application_context)

    @protected
    async def boundary() -> str:
        return "ok"

    assert await aspect.around_async(boundary) == "ok"


@pytest.mark.parametrize(
    "requirement",
    [
        AuthRequirement(kind=AuthRequirementKind.PERMISSION, ref="documents:read"),
        AuthRequirement(kind=AuthRequirementKind.POLICY, ref="document:1"),
        AuthRequirement(kind=AuthRequirementKind.RELATION, ref="owner"),
        AuthRequirement(kind=AuthRequirementKind.ROLE, ref="role:admin"),
        AuthRequirement(kind=AuthRequirementKind.SCOPE, ref="documents:read"),
    ],
)
def test_missing_requirement_provider_fails_closed(
    requirement: AuthRequirement,
) -> None:
    application_context = _context_with_auth()
    aspect = AuthorizationAspect(application_context)

    with pytest.raises(AuthRequirementProviderUnavailableError):
        aspect._evaluate_requirement(
            requirement,
            AuthContext(subject=AuthSubject(id="user:1"), issuer="issuer:1"),
        )


@pytest.mark.parametrize(
    "requirement",
    [
        AuthRequirement(kind=AuthRequirementKind.PERMISSION, ref="documents:read"),
        AuthRequirement(kind=AuthRequirementKind.POLICY, ref="document:1"),
        AuthRequirement(kind=AuthRequirementKind.RELATION, ref="owner"),
        AuthRequirement(kind=AuthRequirementKind.ROLE, ref="role:admin"),
        AuthRequirement(kind=AuthRequirementKind.SCOPE, ref="documents:read"),
    ],
)
def test_async_missing_requirement_provider_fails_closed(
    requirement: AuthRequirement,
) -> None:
    application_context = _context_with_auth()
    aspect = AsyncAuthorizationAspect(application_context)

    with pytest.raises(AuthRequirementProviderUnavailableError):
        aspect._evaluate_requirement(
            requirement,
            AuthContext(subject=AuthSubject(id="user:1"), issuer="issuer:1"),
        )


def test_invalid_policy_and_relation_requirements_fail_closed() -> None:
    application_context = _context_with_auth()
    auth_context = AuthContext(subject=AuthSubject(id="user:1"), issuer="issuer:1")
    sync_aspect = AuthorizationAspect(
        application_context,
        authorization_policy_evaluator=AllowingAuthorizationPolicyEvaluator(),
        relation_checker=AllowingRelationChecker(),
    )
    async_aspect = AsyncAuthorizationAspect(
        application_context,
        authorization_policy_evaluator=AllowingAuthorizationPolicyEvaluator(),
        relation_checker=AllowingRelationChecker(),
    )

    for aspect in (sync_aspect, async_aspect):
        with pytest.raises(AuthRequirementProviderUnavailableError):
            aspect._evaluate_requirement(
                AuthRequirement(kind=AuthRequirementKind.POLICY, ref="document:1"),
                auth_context,
            )
        with pytest.raises(AuthRequirementProviderUnavailableError):
            aspect._evaluate_requirement(
                AuthRequirement(kind=AuthRequirementKind.RELATION, ref="owner"),
                auth_context,
            )


def test_auth_pointcuts_distinguish_sync_and_async_boundaries() -> None:
    @require_scope("documents:read")
    def sync_boundary() -> str:
        return "ok"

    @require_scope("documents:read")
    async def async_boundary() -> str:
        return "ok"

    assert _matches_sync(sync_boundary)
    assert not _matches_sync(async_boundary)
    assert _matches_async(async_boundary)
    assert not _matches_async(sync_boundary)


def _context_with_auth() -> ApplicationContext:
    application_context = ApplicationContext()
    store_auth_context(
        application_context,
        AuthContext(
            subject=AuthSubject(id="user:1"),
            issuer="issuer:1",
            tenant="tenant:1",
            roles=("role:admin",),
            scopes=("documents:read",),
        ),
    )
    return application_context
