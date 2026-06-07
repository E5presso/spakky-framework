"""AOP enforcement for protected auth metadata."""

from inspect import iscoroutinefunction
from typing import override

from spakky.auth.context import AuthContext, require_auth_context
from spakky.auth.decision import AuthorizationDecision, AuthorizationDecisionState
from spakky.auth.error import (
    AuthContextNotFoundError,
    AuthRequirementDeniedError,
    AuthRequirementProviderUnavailableError,
)
from spakky.auth.metadata import (
    AuthRequirement,
    AuthRequirementKind,
    get_effective_auth_metadata,
    has_auth_boundary_metadata,
)
from spakky.auth.ports import (
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
)
from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.aop.pointcut import Around
from spakky.core.common.types import AsyncFunc, Func
from spakky.core.pod.annotations.order import Order
from spakky.core.pod.interfaces.aware.application_context_aware import (
    IApplicationContextAware,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext


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

    def __init__(
        self,
        application_context: IApplicationContext | None = None,
        authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None = None,
        permission_checker: IPermissionChecker | None = None,
        relation_checker: IRelationChecker | None = None,
        role_checker: IRoleChecker | None = None,
        scope_checker: IScopeChecker | None = None,
    ) -> None:
        self._application_context = application_context
        self._authorization_policy_evaluator = authorization_policy_evaluator
        self._permission_checker = permission_checker
        self._relation_checker = relation_checker
        self._role_checker = role_checker
        self._scope_checker = scope_checker

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
                    tenant=requirement.tenant,
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
                    tenant=requirement.tenant,
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
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.ROLE:
            if self._role_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._role_checker.check_role(
                RoleCheckRequest(
                    auth_context=auth_context,
                    role=requirement.ref,
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.SCOPE:
            if self._scope_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._scope_checker.check_scope(
                ScopeCheckRequest(auth_context=auth_context, scope=requirement.ref)
            )
        raise AuthRequirementProviderUnavailableError()  # pragma: no cover - exhaustive AuthRequirementKind guard

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

    def __init__(
        self,
        application_context: IApplicationContext | None = None,
        authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None = None,
        permission_checker: IPermissionChecker | None = None,
        relation_checker: IRelationChecker | None = None,
        role_checker: IRoleChecker | None = None,
        scope_checker: IScopeChecker | None = None,
    ) -> None:
        self._application_context = application_context
        self._authorization_policy_evaluator = authorization_policy_evaluator
        self._permission_checker = permission_checker
        self._relation_checker = relation_checker
        self._role_checker = role_checker
        self._scope_checker = scope_checker

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
            decision = self._evaluate_requirement(requirement, auth_context)
            if decision.state is not AuthorizationDecisionState.ALLOW:
                raise AuthRequirementDeniedError(decision)
        return await joinpoint(*args, **kwargs)

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
                    tenant=requirement.tenant,
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
                    tenant=requirement.tenant,
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
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.ROLE:
            if self._role_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._role_checker.check_role(
                RoleCheckRequest(
                    auth_context=auth_context,
                    role=requirement.ref,
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.SCOPE:
            if self._scope_checker is None:
                raise AuthRequirementProviderUnavailableError()
            return self._scope_checker.check_scope(
                ScopeCheckRequest(auth_context=auth_context, scope=requirement.ref)
            )
        raise AuthRequirementProviderUnavailableError()  # pragma: no cover - exhaustive AuthRequirementKind guard

    def _required_application_context(self) -> IApplicationContext:
        if self._application_context is None:
            raise AuthContextNotFoundError()
        return self._application_context
