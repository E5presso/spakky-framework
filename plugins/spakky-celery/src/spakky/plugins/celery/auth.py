"""Auth snapshot propagation and enforcement for Celery task boundaries."""

from spakky.auth import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    EXPIRED_SNAPSHOT_DECISION,
    INVALID_SNAPSHOT_DECISION,
    MISSING_SNAPSHOT_DECISION,
    VERIFICATION_PROVIDER_UNAVAILABLE_DECISION,
    AuthContext,
    AuthInvocation,
    AuthInvocationAttribute,
    AuthRequirementDeniedError,
    AuthSnapshotPropagationConfig,
    AuthVerificationProviderUnavailableError,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthorizationRequest,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotSigner,
    IAuthContextSnapshotVerifier,
    IAuthorizationPolicyEvaluator,
    IPermissionChecker,
    IRelationChecker,
    IRoleChecker,
    IScopeChecker,
    InvalidAuthContextSnapshotError,
    InvalidAuthContextValueError,
    MissingAuthContextSnapshotError,
    PermissionCheckRequest,
    RelationCheckRequest,
    RoleCheckRequest,
    ScopeCheckRequest,
    SnapshotSignRequest,
    store_auth_context,
)
from spakky.core.pod.interfaces.application_context import IApplicationContext
from spakky.task.stereotype.task_handler import (
    TaskAuthMetadata,
    TaskAuthRequirementMetadata,
)

from spakky.plugins.celery.error import AuthSnapshotPropagationSignerUnavailableError

CELERY_AUTH_BOUNDARY = "task"
"""AuthInvocation boundary value used for Celery task workers."""


def inject_auth_context_snapshot(
    headers: dict[str, str],
    *,
    application_context: IApplicationContext,
    auth_snapshot_signer: IAuthContextSnapshotSigner | None,
    auth_snapshot_propagation_config: AuthSnapshotPropagationConfig,
) -> None:
    """Inject a signed AuthContextSnapshot into Celery task headers."""
    if not auth_snapshot_propagation_config.enabled:
        return
    value = application_context.get_context_value(AUTH_CONTEXT_CONTEXT_KEY)
    if value is None:
        return
    if not isinstance(value, AuthContext):
        raise InvalidAuthContextValueError()
    if auth_snapshot_signer is None:
        raise AuthSnapshotPropagationSignerUnavailableError()
    snapshot = auth_snapshot_signer.sign_snapshot(
        SnapshotSignRequest(auth_context=value)
    )
    headers[AUTH_CONTEXT_SNAPSHOT_METADATA_KEY] = snapshot.base64url_canonical_json()


def seed_and_authorize_celery_task(
    *,
    application_context: IApplicationContext,
    task_name: str,
    headers: dict[str, str],
    auth_metadata: TaskAuthMetadata,
    snapshot_verifier: IAuthContextSnapshotVerifier | None,
    authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None,
    permission_checker: IPermissionChecker | None,
    relation_checker: IRelationChecker | None,
    role_checker: IRoleChecker | None,
    scope_checker: IScopeChecker | None,
) -> None:
    """Verify a worker snapshot, seed AuthContext, and enforce task metadata."""
    if not auth_metadata.protected:
        return
    invocation = AuthInvocation(
        boundary=CELERY_AUTH_BOUNDARY,
        operation=task_name,
        attributes=(
            AuthInvocationAttribute(
                name="auth_context_snapshot",
                value=headers.get(AUTH_CONTEXT_SNAPSHOT_METADATA_KEY),
            ),
        ),
    )
    auth_context = _verify_snapshot(
        headers.get(AUTH_CONTEXT_SNAPSHOT_METADATA_KEY),
        invocation,
        snapshot_verifier,
    )
    store_auth_context(application_context, auth_context)
    for requirement in auth_metadata.requirements:
        decision = _evaluate_requirement(
            requirement,
            auth_context,
            authorization_policy_evaluator=authorization_policy_evaluator,
            permission_checker=permission_checker,
            relation_checker=relation_checker,
            role_checker=role_checker,
            scope_checker=scope_checker,
        )
        if decision.state is not AuthorizationDecisionState.ALLOW:
            raise AuthRequirementDeniedError(decision)


def is_retryable_auth_failure(error: AuthRequirementDeniedError) -> bool:
    """Return whether a task auth failure should use Celery retry semantics."""
    return (
        error.decision is not None
        and error.decision.state is AuthorizationDecisionState.ERROR
    )


def _verify_snapshot(
    snapshot_envelope: str | None,
    invocation: AuthInvocation,
    snapshot_verifier: IAuthContextSnapshotVerifier | None,
) -> AuthContext:
    if snapshot_envelope is None or snapshot_envelope == "":
        raise AuthRequirementDeniedError(MISSING_SNAPSHOT_DECISION)
    if snapshot_verifier is None:
        raise AuthRequirementDeniedError(VERIFICATION_PROVIDER_UNAVAILABLE_DECISION)
    try:
        return snapshot_verifier.verify_snapshot(snapshot_envelope, invocation)
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
    requirement: TaskAuthRequirementMetadata,
    auth_context: AuthContext,
    *,
    authorization_policy_evaluator: IAuthorizationPolicyEvaluator | None,
    permission_checker: IPermissionChecker | None,
    relation_checker: IRelationChecker | None,
    role_checker: IRoleChecker | None,
    scope_checker: IScopeChecker | None,
) -> AuthorizationDecision:
    if requirement.kind == "AUTHENTICATED":
        return AuthorizationDecision.allow()
    if requirement.kind == "PERMISSION":
        if permission_checker is None:
            return _provider_unavailable_decision()
        return permission_checker.check_permission(
            PermissionCheckRequest(
                auth_context=auth_context,
                permission=requirement.ref,
                resource=requirement.resource,
                tenant=requirement.tenant,
            )
        )
    if requirement.kind == "POLICY":
        if (
            authorization_policy_evaluator is None
            or requirement.resource is None
            or requirement.action is None
        ):
            return _provider_unavailable_decision()
        return authorization_policy_evaluator.evaluate_policy(
            AuthorizationRequest(
                auth_context=auth_context,
                resource=requirement.resource,
                action=requirement.action,
                tenant=requirement.tenant,
            )
        )
    if requirement.kind == "RELATION":
        if relation_checker is None or requirement.resource is None:
            return _provider_unavailable_decision()
        return relation_checker.check_relation(
            RelationCheckRequest(
                auth_context=auth_context,
                relation=requirement.ref,
                resource=requirement.resource,
                tenant=requirement.tenant,
            )
        )
    if requirement.kind == "ROLE":
        if role_checker is None:
            return _provider_unavailable_decision()
        return role_checker.check_role(
            RoleCheckRequest(
                auth_context=auth_context,
                role=requirement.ref,
                tenant=requirement.tenant,
            )
        )
    if requirement.kind == "SCOPE":
        if scope_checker is None:
            return _provider_unavailable_decision()
        return scope_checker.check_scope(
            ScopeCheckRequest(auth_context=auth_context, scope=requirement.ref)
        )
    return _provider_unavailable_decision()


def _provider_unavailable_decision() -> AuthorizationDecision:
    return AuthorizationDecision.error(
        AuthorizationReasonCode.INTERNAL_ERROR,
        reason="Celery task auth provider is unavailable",
    )
