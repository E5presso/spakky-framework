"""Saga auth snapshot verification and protected step enforcement."""

from dataclasses import dataclass

from spakky.auth import (
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
    AuthContext,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthRequirement,
    AuthRequirementDeniedError,
    AuthRequirementKind,
    AuthVerificationProviderUnavailableError,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthorizationRequest,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotVerifier,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRelationChecker,
    IRoleChecker,
    IScopeChecker,
    InvalidAuthContextSnapshotError,
    MissingAuthContextSnapshotError,
    PermissionCheckRequest,
    RelationCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
    get_effective_auth_metadata,
)
from spakky.saga.data import AbstractSagaData

SAGA_AUTH_BOUNDARY = "saga"
"""AuthInvocation boundary value used for protected saga steps."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SagaAuthExecutionContext:
    """Provider-neutral auth ports used while executing protected saga steps."""

    snapshot_verifier: IAuthContextSnapshotVerifier | None = None
    authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None = None
    permission_checker: IPermissionChecker | None = None
    relation_checker: IRelationChecker | None = None
    role_checker: IRoleChecker | None = None
    scope_checker: IScopeChecker | None = None

    def authorize_step(
        self,
        *,
        step_name: str,
        boundary: object | None,
        owner_type: type[object] | None,
        data: AbstractSagaData,
    ) -> None:
        """Authorize a saga step when protected auth metadata is present."""
        if boundary is None:
            return
        metadata = get_effective_auth_metadata(boundary, owner_type=owner_type)
        if not metadata.protected:
            return
        invocation = self._invocation(step_name, data)
        auth_context = self._verify_snapshot(data.auth_context_snapshot, invocation)
        for requirement in metadata.requirements:
            decision = self._evaluate_requirement(requirement, auth_context)
            if decision.state is not AuthorizationDecisionState.ALLOW:
                raise AuthRequirementDeniedError(decision)

    def _verify_snapshot(
        self,
        snapshot_envelope: str | None,
        invocation: AuthInvocation,
    ) -> AuthContext:
        if snapshot_envelope is None or snapshot_envelope == "":
            raise AuthRequirementDeniedError(MISSING_SNAPSHOT_DECISION)
        if self.snapshot_verifier is None:
            raise AuthRequirementDeniedError(VERIFICATION_PROVIDER_UNAVAILABLE_DECISION)
        try:
            return self.snapshot_verifier.verify_snapshot(snapshot_envelope, invocation)
        except MissingAuthContextSnapshotError as error:
            raise AuthRequirementDeniedError(MISSING_SNAPSHOT_DECISION) from error
        except InvalidAuthContextSnapshotError as error:
            raise AuthRequirementDeniedError(INVALID_SNAPSHOT_DECISION) from error
        except ExpiredAuthContextSnapshotError as error:
            raise AuthRequirementDeniedError(EXPIRED_SNAPSHOT_DECISION) from error
        except AuthVerificationProviderUnavailableError as error:
            raise AuthRequirementDeniedError(
                VERIFICATION_PROVIDER_UNAVAILABLE_DECISION
            ) from error

    def _evaluate_requirement(
        self,
        requirement: AuthRequirement,
        auth_context: AuthContext,
    ) -> AuthorizationDecision:
        if requirement.kind is AuthRequirementKind.AUTHENTICATED:
            return AuthorizationDecision.allow()
        if requirement.kind is AuthRequirementKind.PERMISSION:
            checker = self.permission_checker
            if checker is None:
                return _provider_unavailable_decision()
            return checker.check_permission(
                PermissionCheckRequest(
                    auth_context=auth_context,
                    permission=requirement.ref,
                    resource=requirement.resource,
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.POLICY:
            evaluator = self.authorization_policy_evaluator
            if (
                evaluator is None
                or requirement.resource is None
                or requirement.action is None
            ):
                return _provider_unavailable_decision()
            return evaluator.evaluate_policy(
                AuthorizationRequest(
                    auth_context=auth_context,
                    resource=requirement.resource,
                    action=requirement.action,
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.RELATION:
            checker = self.relation_checker
            if checker is None or requirement.resource is None:
                return _provider_unavailable_decision()
            return checker.check_relation(
                RelationCheckRequest(
                    auth_context=auth_context,
                    relation=requirement.ref,
                    resource=requirement.resource,
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.ROLE:
            checker = self.role_checker
            if checker is None:
                return _provider_unavailable_decision()
            return checker.check_role(
                RoleCheckRequest(
                    auth_context=auth_context,
                    role=requirement.ref,
                    tenant=requirement.tenant,
                )
            )
        if requirement.kind is AuthRequirementKind.SCOPE:
            checker = self.scope_checker
            if checker is None:
                return _provider_unavailable_decision()
            return checker.check_scope(
                ScopeCheckRequest(auth_context=auth_context, scope=requirement.ref)
            )
        return (
            _provider_unavailable_decision()
        )  # pragma: no cover - exhaustive AuthRequirementKind guard

    def _invocation(self, step_name: str, data: AbstractSagaData) -> AuthInvocation:
        return AuthInvocation(
            boundary=SAGA_AUTH_BOUNDARY,
            operation=step_name,
            attributes=(
                AuthInvocationAttribute(name="saga_id", value=str(data.saga_id)),
                AuthInvocationAttribute(
                    name="auth_context_snapshot", value=data.auth_context_snapshot
                ),
            ),
        )


def _provider_unavailable_decision() -> AuthorizationDecision:
    return AuthorizationDecision.error(
        AuthorizationReasonCode.INTERNAL_ERROR,
        reason="Saga auth provider is unavailable",
    )
