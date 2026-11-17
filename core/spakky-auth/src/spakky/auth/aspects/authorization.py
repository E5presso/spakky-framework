"""AOP enforcement for protected auth metadata."""

from inspect import iscoroutinefunction
from typing import override

from spakky.auth.context import AuthContext, require_auth_context
from spakky.auth.decision import AuthorizationDecision, AuthorizationDecisionState
from spakky.auth.error import (
    AuthContextNotFoundError,
    AuthDynamicRefUnresolvedError,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
)
from spakky.auth.metadata import (
    AuthRequirement,
    AuthRequirementKind,
    get_effective_auth_metadata,
    has_auth_boundary_metadata,
)
from spakky.auth.invocation import (
    AuthDynamicRef,
    AuthTenantRef,
    get_auth_invocation,
)
from spakky.auth.ports import (
    AuthorizationRequest,
    IAsyncRoleChecker,
    IAuthInvocationResolver,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRelationChecker,
    IRoleChecker,
    IScopeChecker,
    PermissionCheckRequest,
    RelationCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
)
from spakky.auth.resolver import AuthInvocationAttributeResolver
from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext


_DEFAULT_INVOCATION_RESOLVER = AuthInvocationAttributeResolver()
"""Resolver used when the application registers no IAuthInvocationResolver."""


def _matches_sync(boundary: Func) -> bool:
    return has_auth_boundary_metadata(boundary) and not iscoroutinefunction(boundary)


def _matches_async(boundary: Func) -> bool:
    return has_auth_boundary_metadata(boundary) and iscoroutinefunction(boundary)


@Order(0)
@Aspect()
class AuthorizationAspect(IAspect, IApplicationContextAware):
    """Synchronous aspect enforcing protected auth metadata."""

    _application_context: IApplicationContext | None
    _authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None
    _permission_checker: IPermissionChecker | None
    _relation_checker: IRelationChecker | None
    _role_checker: IRoleChecker | None
    _scope_checker: IScopeChecker | None
    _invocation_resolver: IAuthInvocationResolver | None

    def __init__(
        self,
        application_context: IApplicationContext | None = None,
        authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None = None,
        permission_checker: IPermissionChecker | None = None,
        relation_checker: IRelationChecker | None = None,
        role_checker: IRoleChecker | None = None,
        scope_checker: IScopeChecker | None = None,
        invocation_resolver: IAuthInvocationResolver | None = None,
    ) -> None:
        self._application_context = application_context
        self._authorization_policy_evaluator = authorization_policy_evaluator
        self._permission_checker = permission_checker
        self._relation_checker = relation_checker
        self._role_checker = role_checker
        self._scope_checker = scope_checker
        self._invocation_resolver = invocation_resolver

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject the application context when managed as a Pod."""
        self._application_context = application_context

    @Around(_matches_sync)
    @override
    def around(
        self,
        joinpoint: Func,
        *args: object,
        **kwargs: object,
    ) -> object:
        metadata = get_effective_auth_metadata(joinpoint)
        if not metadata.protected:
            return joinpoint(*args, **kwargs)
        auth_context = require_auth_context(self._required_application_context())
        for requirement in metadata.requirements:
            decision = self._evaluate_requirement(requirement, auth_context)
            if decision.state is not AuthorizationDecisionState.ALLOW:
                raise AuthRequirementDeniedError(decision)
        return joinpoint(*args, **kwargs)

    def _evaluate_requirement(
        self,
        requirement: AuthRequirement,
        auth_context: AuthContext,
    ) -> AuthorizationDecision:
        if requirement.kind is AuthRequirementKind.AUTHENTICATED:
            return AuthorizationDecision.allow()
        if requirement.kind is AuthRequirementKind.PERMISSION:
            if self._permission_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._permission_checker.check_permission(
                PermissionCheckRequest(
                    auth_context=auth_context,
                    permission=requirement.ref,
                    resource=requirement.resource,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.POLICY:
            if self._authorization_policy_evaluator is None:
                raise AuthRequirementProviderUnavailableError()
            if requirement.resource is None or requirement.action is None:
                raise AuthRequirementProviderUnavailableError()
            return self._authorization_policy_evaluator.evaluate_policy(
                AuthorizationRequest(
                    auth_context=auth_context,
                    resource=requirement.resource,
                    action=requirement.action,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.RELATION:
            if self._relation_checker is None or requirement.resource is None:
                raise AuthRequirementProviderUnavailableError()
            return self._relation_checker.check_relation(
                RelationCheckRequest(
                    auth_context=auth_context,
                    relation=requirement.ref,
                    resource=requirement.resource,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.ROLE:
            if self._role_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._role_checker.check_role(
                RoleCheckRequest(
                    auth_context=auth_context,
                    role=requirement.ref,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.SCOPE:
            if self._scope_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._scope_checker.check_scope(
                ScopeCheckRequest(auth_context=auth_context, scope=requirement.ref)
            )
        raise AuthRequirementProviderUnavailableError()  # pragma: no cover - exhaustive AuthRequirementKind guard

    def _tenant(self, requirement: AuthRequirement) -> AuthTenantRef | None:
        """Return the tenant a requirement is scoped to for the current invocation.

        Returns:
            The fixed or resolved tenant, or None when the requirement is not
            tenant-scoped.

        Raises:
            AuthDynamicRefUnresolvedError: The tenant is late-bound and the
                boundary stored no invocation, or the resolver answered with
                another reference kind or an empty value.
        """
        tenant = requirement.tenant
        if not isinstance(tenant, AuthDynamicRef):
            return tenant
        invocation = get_auth_invocation(self._required_application_context())
        if invocation is None:
            raise AuthDynamicRefUnresolvedError(tenant.expression)
        resolver = (
            self._invocation_resolver
            if self._invocation_resolver is not None
            else _DEFAULT_INVOCATION_RESOLVER
        )
        resolved = resolver.resolve_ref(invocation, tenant)
        if resolved.kind is not tenant.kind or resolved.value == "":
            raise AuthDynamicRefUnresolvedError(tenant.expression)
        return resolved.value

    def _required_application_context(self) -> IApplicationContext:
        if self._application_context is None:
            raise AuthContextNotFoundError()
        return self._application_context


@Order(0)
@AsyncAspect()
class AsyncAuthorizationAspect(IAsyncAspect, IApplicationContextAware):
    """Asynchronous aspect enforcing protected auth metadata."""

    _application_context: IApplicationContext | None
    _authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None
    _permission_checker: IPermissionChecker | None
    _relation_checker: IRelationChecker | None
    _role_checker: IRoleChecker | None
    _scope_checker: IScopeChecker | None
    _invocation_resolver: IAuthInvocationResolver | None
    _async_role_checker: IAsyncRoleChecker | None

    def __init__(
        self,
        application_context: IApplicationContext | None = None,
        authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None = None,
        permission_checker: IPermissionChecker | None = None,
        relation_checker: IRelationChecker | None = None,
        role_checker: IRoleChecker | None = None,
        scope_checker: IScopeChecker | None = None,
        invocation_resolver: IAuthInvocationResolver | None = None,
        async_role_checker: IAsyncRoleChecker | None = None,
    ) -> None:
        self._application_context = application_context
        self._authorization_policy_evaluator = authorization_policy_evaluator
        self._permission_checker = permission_checker
        self._relation_checker = relation_checker
        self._role_checker = role_checker
        self._scope_checker = scope_checker
        self._invocation_resolver = invocation_resolver
        self._async_role_checker = async_role_checker

    @override
    def set_application_context(self, application_context: IApplicationContext) -> None:
        """Inject the application context when managed as a Pod."""
        self._application_context = application_context

    @Around(_matches_async)
    @override
    async def around_async(
        self,
        joinpoint: AsyncFunc,
        *args: object,
        **kwargs: object,
    ) -> object:
        metadata = get_effective_auth_metadata(joinpoint)
        if not metadata.protected:
            return await joinpoint(*args, **kwargs)
        auth_context = require_auth_context(self._required_application_context())
        for requirement in metadata.requirements:
            decision = await self._evaluate_requirement_async(requirement, auth_context)
            if decision.state is not AuthorizationDecisionState.ALLOW:
                raise AuthRequirementDeniedError(decision)
        return await joinpoint(*args, **kwargs)

    async def _evaluate_requirement_async(
        self,
        requirement: AuthRequirement,
        auth_context: AuthContext,
    ) -> AuthorizationDecision:
        """Evaluate a requirement, awaiting the async role checker when present."""
        if (
            requirement.kind is AuthRequirementKind.ROLE
            and self._async_role_checker is not None
        ):
            return await self._async_role_checker.check_role(
                RoleCheckRequest(
                    auth_context=auth_context,
                    role=requirement.ref,
                    tenant=self._tenant(requirement),
                )
            )
        return self._evaluate_requirement(requirement, auth_context)

    def _evaluate_requirement(
        self,
        requirement: AuthRequirement,
        auth_context: AuthContext,
    ) -> AuthorizationDecision:
        if requirement.kind is AuthRequirementKind.AUTHENTICATED:
            return AuthorizationDecision.allow()
        if requirement.kind is AuthRequirementKind.PERMISSION:
            if self._permission_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._permission_checker.check_permission(
                PermissionCheckRequest(
                    auth_context=auth_context,
                    permission=requirement.ref,
                    resource=requirement.resource,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.POLICY:
            if self._authorization_policy_evaluator is None:
                raise AuthRequirementProviderUnavailableError()
            if requirement.resource is None or requirement.action is None:
                raise AuthRequirementProviderUnavailableError()
            return self._authorization_policy_evaluator.evaluate_policy(
                AuthorizationRequest(
                    auth_context=auth_context,
                    resource=requirement.resource,
                    action=requirement.action,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.RELATION:
            if self._relation_checker is None or requirement.resource is None:
                raise AuthRequirementProviderUnavailableError()
            return self._relation_checker.check_relation(
                RelationCheckRequest(
                    auth_context=auth_context,
                    relation=requirement.ref,
                    resource=requirement.resource,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.ROLE:
            if self._role_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._role_checker.check_role(
                RoleCheckRequest(
                    auth_context=auth_context,
                    role=requirement.ref,
                    tenant=self._tenant(requirement),
                )
            )
        if requirement.kind is AuthRequirementKind.SCOPE:
            if self._scope_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._scope_checker.check_scope(
                ScopeCheckRequest(auth_context=auth_context, scope=requirement.ref)
            )
        raise AuthRequirementProviderUnavailableError()  # pragma: no cover - exhaustive AuthRequirementKind guard

    def _tenant(self, requirement: AuthRequirement) -> AuthTenantRef | None:
        """Return the tenant a requirement is scoped to for the current invocation.

        Returns:
            The fixed or resolved tenant, or None when the requirement is not
            tenant-scoped.

        Raises:
            AuthDynamicRefUnresolvedError: The tenant is late-bound and the
                boundary stored no invocation, or the resolver answered with
                another reference kind or an empty value.
        """
        tenant = requirement.tenant
        if not isinstance(tenant, AuthDynamicRef):
            return tenant
        invocation = get_auth_invocation(self._required_application_context())
        if invocation is None:
            raise AuthDynamicRefUnresolvedError(tenant.expression)
        resolver = (
            self._invocation_resolver
            if self._invocation_resolver is not None
            else _DEFAULT_INVOCATION_RESOLVER
        )
        resolved = resolver.resolve_ref(invocation, tenant)
        if resolved.kind is not tenant.kind or resolved.value == "":
            raise AuthDynamicRefUnresolvedError(tenant.expression)
        return resolved.value

    def _required_application_context(self) -> IApplicationContext:
        if self._application_context is None:
            raise AuthContextNotFoundError()
        return self._application_context
