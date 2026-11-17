from typing import override

import pytest

from spakky.auth import (
    AuthContext,
    AuthDynamicRef,
    AuthDynamicRefKind,
    AuthDynamicRefUnresolvedError,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthInvocationAttributeResolver,
    AuthRequirement,
    AuthRequirementDeniedError,
    AuthRequirementKind,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthorizationRequest,
    IAsyncRoleChecker,
    IAuthInvocationResolver,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRelationChecker,
    IRoleChecker,
    InvalidAuthDynamicRefKindError,
    PermissionCheckRequest,
    RelationCheckRequest,
    ResolvedAuthReference,
    RoleCheckRequest,
    get_auth_invocation,
    require_permission,
    require_policy,
    require_relation,
    require_role,
    store_auth_context,
    store_auth_invocation,
)
from spakky.auth.aspects.authorization import (
    AsyncAuthorizationAspect,
    AuthorizationAspect,
)
from spakky.core.application.application_context import ApplicationContext

WORKSPACE_HEADER = "http.header.x-workspace"


class RecordingRoleChecker(IRoleChecker):
    requests: list[RoleCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class RecordingAsyncRoleChecker(IAsyncRoleChecker):
    requests: list[RoleCheckRequest]
    decision: AuthorizationDecision

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.requests = []
        self.decision = decision

    @override
    async def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return self.decision


class RecordingPermissionChecker(IPermissionChecker):
    requests: list[PermissionCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def check_permission(
        self, request: PermissionCheckRequest
    ) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class RecordingPolicyEvaluator(IAuthorizationPolicyEvaluator):
    requests: list[AuthorizationRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class RecordingRelationChecker(IRelationChecker):
    requests: list[RelationCheckRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def check_relation(self, request: RelationCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return AuthorizationDecision.allow()


class FixedResolver(IAuthInvocationResolver):
    resolved: ResolvedAuthReference

    def __init__(self, resolved: ResolvedAuthReference) -> None:
        self.resolved = resolved

    @override
    def resolve_ref(
        self,
        invocation: AuthInvocation,
        dynamic_ref: AuthDynamicRef,
    ) -> ResolvedAuthReference:
        return self.resolved


def _context(
    *attributes: AuthInvocationAttribute,
    with_invocation: bool = True,
) -> ApplicationContext:
    application_context = ApplicationContext()
    store_auth_context(
        application_context,
        AuthContext(subject=AuthSubject(id="user:1"), issuer="issuer"),
    )
    if with_invocation:
        store_auth_invocation(
            application_context,
            AuthInvocation(
                boundary="HTTP",
                operation="GET /documents",
                attributes=attributes,
            ),
        )
    return application_context


def _workspace(value: str | int | None) -> AuthInvocationAttribute:
    return AuthInvocationAttribute(name=WORKSPACE_HEADER, value=value)


def test_dynamic_ref_tenant_factory_expect_tenant_kind() -> None:
    """AuthDynamicRef.tenant()는 TENANT 종류의 동적 참조를 만든다."""
    ref = AuthDynamicRef.tenant(WORKSPACE_HEADER)

    assert ref == AuthDynamicRef(
        kind=AuthDynamicRefKind.TENANT, expression=WORKSPACE_HEADER
    )


def test_requirement_with_non_tenant_dynamic_ref_expect_invalid_kind_error() -> None:
    """tenant 자리에 TENANT가 아닌 동적 참조를 선언하면 선언 시점에 거부한다."""
    with pytest.raises(InvalidAuthDynamicRefKindError):
        AuthRequirement(
            kind=AuthRequirementKind.ROLE,
            ref="role:member",
            tenant=AuthDynamicRef(
                kind=AuthDynamicRefKind.RESOURCE, expression=WORKSPACE_HEADER
            ),
        )


def test_auth_invocation_round_trips_through_application_context() -> None:
    """저장한 AuthInvocation을 ApplicationContext에서 다시 읽는다."""
    application_context = ApplicationContext()
    invocation = AuthInvocation(boundary="HTTP", operation="GET /")

    assert get_auth_invocation(application_context) is None
    store_auth_invocation(application_context, invocation)

    assert get_auth_invocation(application_context) == invocation


def test_attribute_resolver_expect_named_attribute_value() -> None:
    """기본 resolver는 expression과 이름이 같은 속성 값을 참조 값으로 돌려준다."""
    resolved = AuthInvocationAttributeResolver().resolve_ref(
        AuthInvocation(
            boundary="HTTP",
            operation="GET /",
            attributes=(
                AuthInvocationAttribute(name="handler", value="Controller.get"),
                _workspace("workspace:1"),
            ),
        ),
        AuthDynamicRef.tenant(WORKSPACE_HEADER),
    )

    assert resolved == ResolvedAuthReference(
        kind=AuthDynamicRefKind.TENANT, value="workspace:1"
    )


@pytest.mark.parametrize("value", [None, "", 7])
def test_attribute_resolver_with_unusable_value_expect_unresolved(
    value: str | int | None,
) -> None:
    """속성이 비었거나 문자열이 아니면 해석하지 못한 것으로 거부한다."""
    with pytest.raises(AuthDynamicRefUnresolvedError) as error:
        AuthInvocationAttributeResolver().resolve_ref(
            AuthInvocation(
                boundary="HTTP", operation="GET /", attributes=(_workspace(value),)
            ),
            AuthDynamicRef.tenant(WORKSPACE_HEADER),
        )

    assert error.value.expression == WORKSPACE_HEADER
    assert error.value.decision is not None
    assert error.value.decision.state is AuthorizationDecisionState.DENY
    assert (
        error.value.decision.reason_code
        is AuthorizationReasonCode.DYNAMIC_REF_UNRESOLVED
    )


def test_sync_aspect_with_dynamic_tenant_expect_resolved_tenant_in_every_request() -> (
    None
):
    """동적 tenant는 role·permission·policy·relation 요청에 해석된 값으로 전달된다."""
    role_checker = RecordingRoleChecker()
    permission_checker = RecordingPermissionChecker()
    policy_evaluator = RecordingPolicyEvaluator()
    relation_checker = RecordingRelationChecker()
    aspect = AuthorizationAspect(
        _context(_workspace("workspace:1")),
        authorization_policy_evaluator=policy_evaluator,
        permission_checker=permission_checker,
        relation_checker=relation_checker,
        role_checker=role_checker,
    )
    tenant = AuthDynamicRef.tenant(WORKSPACE_HEADER)

    @require_relation("owner", resource="document:1", tenant=tenant)
    @require_policy("document:1", "read", tenant=tenant)
    @require_permission("documents:read", tenant=tenant)
    @require_role("role:member", tenant=tenant)
    def boundary() -> str:
        return "ok"

    assert aspect.around(boundary) == "ok"
    assert role_checker.requests[0].tenant == "workspace:1"
    assert permission_checker.requests[0].tenant == "workspace:1"
    assert policy_evaluator.requests[0].tenant == "workspace:1"
    assert relation_checker.requests[0].tenant == "workspace:1"


def test_sync_aspect_with_missing_attribute_expect_denied_before_checker() -> None:
    """요청에 tenant 속성이 없으면 checker를 부르지 않고 거부한다."""
    role_checker = RecordingRoleChecker()
    aspect = AuthorizationAspect(_context(), role_checker=role_checker)

    @require_role("role:member", tenant=AuthDynamicRef.tenant(WORKSPACE_HEADER))
    def boundary() -> str:
        return "ok"

    with pytest.raises(AuthRequirementDeniedError):
        aspect.around(boundary)
    assert role_checker.requests == []


def test_sync_aspect_without_stored_invocation_expect_unresolved() -> None:
    """경계가 AuthInvocation을 저장하지 않았으면 동적 tenant를 거부한다."""
    aspect = AuthorizationAspect(
        _context(with_invocation=False), role_checker=RecordingRoleChecker()
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant(WORKSPACE_HEADER))
    def boundary() -> str:
        return "ok"

    with pytest.raises(AuthDynamicRefUnresolvedError):
        aspect.around(boundary)


def test_sync_aspect_with_custom_resolver_expect_its_value() -> None:
    """등록된 IAuthInvocationResolver가 있으면 기본 resolver 대신 쓴다."""
    role_checker = RecordingRoleChecker()
    aspect = AuthorizationAspect(
        _context(),
        role_checker=role_checker,
        invocation_resolver=FixedResolver(
            ResolvedAuthReference(kind=AuthDynamicRefKind.TENANT, value="custom:9")
        ),
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant("anything"))
    def boundary() -> str:
        return "ok"

    assert aspect.around(boundary) == "ok"
    assert role_checker.requests[0].tenant == "custom:9"


@pytest.mark.parametrize(
    "resolved",
    [
        ResolvedAuthReference(kind=AuthDynamicRefKind.RESOURCE, value="document:1"),
        ResolvedAuthReference(kind=AuthDynamicRefKind.TENANT, value=""),
    ],
)
def test_sync_aspect_with_wrong_resolver_answer_expect_unresolved(
    resolved: ResolvedAuthReference,
) -> None:
    """resolver가 다른 종류나 빈 값을 돌려주면 거부한다."""
    aspect = AuthorizationAspect(
        _context(),
        role_checker=RecordingRoleChecker(),
        invocation_resolver=FixedResolver(resolved),
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant("anything"))
    def boundary() -> str:
        return "ok"

    with pytest.raises(AuthDynamicRefUnresolvedError):
        aspect.around(boundary)


@pytest.mark.asyncio
async def test_async_aspect_with_async_role_checker_expect_awaited_and_preferred() -> (
    None
):
    """비동기 aspect는 IAsyncRoleChecker를 await하고 동기 checker보다 먼저 쓴다."""
    sync_checker = RecordingRoleChecker()
    async_checker = RecordingAsyncRoleChecker(AuthorizationDecision.allow())
    aspect = AsyncAuthorizationAspect(
        _context(_workspace("workspace:1")),
        role_checker=sync_checker,
        async_role_checker=async_checker,
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant(WORKSPACE_HEADER))
    async def boundary() -> str:
        return "ok"

    assert await aspect.around_async(boundary) == "ok"
    assert async_checker.requests[0].role == "role:member"
    assert async_checker.requests[0].tenant == "workspace:1"
    assert sync_checker.requests == []


@pytest.mark.asyncio
async def test_async_aspect_with_denying_async_role_checker_expect_denied() -> None:
    """IAsyncRoleChecker가 허용하지 않으면 joinpoint 전에 거부한다."""
    aspect = AsyncAuthorizationAspect(
        _context(),
        async_role_checker=RecordingAsyncRoleChecker(
            AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_ROLE)
        ),
    )
    called: list[str] = []

    @require_role("role:member")
    async def boundary() -> str:
        called.append("joinpoint")
        return "ok"

    with pytest.raises(AuthRequirementDeniedError):
        await aspect.around_async(boundary)
    assert called == []


@pytest.mark.asyncio
async def test_async_aspect_without_async_role_checker_expect_sync_checker() -> None:
    """IAsyncRoleChecker가 없으면 비동기 aspect는 동기 IRoleChecker를 쓴다."""
    sync_checker = RecordingRoleChecker()
    aspect = AsyncAuthorizationAspect(
        _context(_workspace("workspace:1")), role_checker=sync_checker
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant(WORKSPACE_HEADER))
    async def boundary() -> str:
        return "ok"

    assert await aspect.around_async(boundary) == "ok"
    assert sync_checker.requests[0].tenant == "workspace:1"


@pytest.mark.asyncio
async def test_async_aspect_without_stored_invocation_expect_unresolved() -> None:
    """비동기 경계도 AuthInvocation이 없으면 checker를 부르지 않고 거부한다."""
    async_checker = RecordingAsyncRoleChecker(AuthorizationDecision.allow())
    aspect = AsyncAuthorizationAspect(
        _context(with_invocation=False), async_role_checker=async_checker
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant(WORKSPACE_HEADER))
    async def boundary() -> str:
        return "ok"

    with pytest.raises(AuthDynamicRefUnresolvedError):
        await aspect.around_async(boundary)
    assert async_checker.requests == []


@pytest.mark.asyncio
async def test_async_aspect_with_wrong_resolver_answer_expect_unresolved() -> None:
    """비동기 경계도 resolver가 다른 종류를 돌려주면 거부한다."""
    aspect = AsyncAuthorizationAspect(
        _context(),
        async_role_checker=RecordingAsyncRoleChecker(AuthorizationDecision.allow()),
        invocation_resolver=FixedResolver(
            ResolvedAuthReference(kind=AuthDynamicRefKind.ACTION, value="read")
        ),
    )

    @require_role("role:member", tenant=AuthDynamicRef.tenant("anything"))
    async def boundary() -> str:
        return "ok"

    with pytest.raises(AuthDynamicRefUnresolvedError):
        await aspect.around_async(boundary)
