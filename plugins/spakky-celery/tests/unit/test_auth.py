"""Tests for Celery auth snapshot propagation helpers."""

from datetime import UTC, datetime
from typing import override
from unittest.mock import MagicMock

import pytest
from spakky.auth import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthContextSnapshot,
    AuthContextSnapshotSignature,
    AuthInvocation,
    AuthRequirementDeniedError,
    AuthSnapshotPropagationConfig,
    AuthSubject,
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
)
from spakky.task.stereotype.task_handler import (
    TaskAuthMetadata,
    TaskAuthRequirementMetadata,
)

from spakky.plugins.celery.auth import (
    inject_auth_context_snapshot,
    is_retryable_auth_failure,
    seed_and_authorize_celery_task,
)
from spakky.plugins.celery.error import AuthSnapshotPropagationSignerUnavailableError


def _auth_context() -> AuthContext:
    return AuthContext(subject=AuthSubject(id="subject-1"), issuer="issuer-1")


class SnapshotSigner(IAuthContextSnapshotSigner):
    @override
    def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
        return AuthContextSnapshot(
            subject=request.auth_context.subject,
            issuer=request.auth_context.issuer,
            issued_at=datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC),
            expires_at=datetime(2026, 5, 15, 1, 7, 3, tzinfo=UTC),
            signature=AuthContextSnapshotSignature(
                key_id="key:test",
                algorithm="HS256",
                signature="signature-1",
            ),
        )


class SnapshotVerifier(IAuthContextSnapshotVerifier):
    error: Exception | None

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    @override
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        if self.error is not None:
            raise self.error
        return _auth_context()


class PolicyEvaluator(IAuthorizationPolicyEvaluator):
    @override
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class PermissionChecker(IPermissionChecker):
    @override
    def check_permission(
        self, request: PermissionCheckRequest
    ) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class RelationChecker(IRelationChecker):
    @override
    def check_relation(self, request: RelationCheckRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class RoleChecker(IRoleChecker):
    @override
    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class ScopeChecker(IScopeChecker):
    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


def _application_context_with(value: object | None) -> MagicMock:
    application_context = MagicMock()
    application_context.get_context_value.return_value = value
    return application_context


def test_inject_auth_snapshot_skips_disabled_config_and_missing_context() -> None:
    """disabled config 또는 missing AuthContext는 snapshot header를 만들지 않는다."""
    headers: dict[str, str] = {}
    disabled_context = _application_context_with(_auth_context())

    inject_auth_context_snapshot(
        headers,
        application_context=disabled_context,
        auth_snapshot_signer=SnapshotSigner(),
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=False),
    )

    assert headers == {}
    disabled_context.get_context_value.assert_not_called()

    inject_auth_context_snapshot(
        headers,
        application_context=_application_context_with(None),
        auth_snapshot_signer=SnapshotSigner(),
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )

    assert headers == {}


def test_inject_auth_snapshot_rejects_invalid_context_value() -> None:
    """AuthContext가 아닌 context value는 invalid context 오류로 실패한다."""
    with pytest.raises(InvalidAuthContextValueError):
        inject_auth_context_snapshot(
            {},
            application_context=_application_context_with("not-auth-context"),
            auth_snapshot_signer=SnapshotSigner(),
            auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(
                enabled=True
            ),
        )


def test_inject_auth_snapshot_requires_signer_when_context_exists() -> None:
    """enabled propagation + AuthContext 조합은 signer provider를 요구한다."""
    with pytest.raises(AuthSnapshotPropagationSignerUnavailableError):
        inject_auth_context_snapshot(
            {},
            application_context=_application_context_with(_auth_context()),
            auth_snapshot_signer=None,
            auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(
                enabled=True
            ),
        )


def test_seed_auth_skips_unprotected_task() -> None:
    """unprotected task metadata는 snapshot verifier 없이 통과한다."""
    application_context = MagicMock()

    seed_and_authorize_celery_task(
        application_context=application_context,
        task_name="tasks.public",
        headers={},
        auth_metadata=TaskAuthMetadata(),
        snapshot_verifier=None,
        authorization_policy_evaluator=None,
        permission_checker=None,
        relation_checker=None,
        role_checker=None,
        scope_checker=None,
    )

    application_context.set_context_value.assert_not_called()


def test_seed_auth_requires_snapshot_verifier_for_protected_task() -> None:
    """protected task는 snapshot verifier provider가 없으면 ERROR decision으로 실패한다."""
    with pytest.raises(AuthRequirementDeniedError) as excinfo:
        seed_and_authorize_celery_task(
            application_context=MagicMock(),
            task_name="tasks.protected",
            headers={AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"},
            auth_metadata=TaskAuthMetadata(
                requirements=(
                    TaskAuthRequirementMetadata(kind="AUTHENTICATED", ref="auth"),
                )
            ),
            snapshot_verifier=None,
            authorization_policy_evaluator=None,
            permission_checker=None,
            relation_checker=None,
            role_checker=None,
            scope_checker=None,
        )

    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state is AuthorizationDecisionState.ERROR


@pytest.mark.parametrize(
    ("verifier_error", "expected_state"),
    [
        (MissingAuthContextSnapshotError(), AuthorizationDecisionState.CHALLENGE),
        (InvalidAuthContextSnapshotError(), AuthorizationDecisionState.CHALLENGE),
        (ExpiredAuthContextSnapshotError(), AuthorizationDecisionState.CHALLENGE),
        (
            AuthVerificationProviderUnavailableError(),
            AuthorizationDecisionState.ERROR,
        ),
    ],
)
def test_seed_auth_maps_snapshot_verifier_errors(
    verifier_error: Exception,
    expected_state: AuthorizationDecisionState,
) -> None:
    """snapshot verifier 오류는 task failure decision으로 매핑된다."""
    with pytest.raises(AuthRequirementDeniedError) as excinfo:
        seed_and_authorize_celery_task(
            application_context=MagicMock(),
            task_name="tasks.protected",
            headers={AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"},
            auth_metadata=TaskAuthMetadata(
                requirements=(
                    TaskAuthRequirementMetadata(kind="AUTHENTICATED", ref="auth"),
                )
            ),
            snapshot_verifier=SnapshotVerifier(verifier_error),
            authorization_policy_evaluator=None,
            permission_checker=None,
            relation_checker=None,
            role_checker=None,
            scope_checker=None,
        )

    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state is expected_state


def test_seed_auth_all_requirement_kinds_allow() -> None:
    """모든 task auth requirement kind가 provider decision으로 평가된다."""
    application_context = MagicMock()

    seed_and_authorize_celery_task(
        application_context=application_context,
        task_name="tasks.protected",
        headers={AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"},
        auth_metadata=TaskAuthMetadata(
            requirements=(
                TaskAuthRequirementMetadata(kind="AUTHENTICATED", ref="auth"),
                TaskAuthRequirementMetadata(kind="PERMISSION", ref="documents:read"),
                TaskAuthRequirementMetadata(
                    kind="POLICY",
                    ref="document-policy",
                    resource="document:1",
                    action="read",
                ),
                TaskAuthRequirementMetadata(
                    kind="RELATION",
                    ref="owner",
                    resource="document:1",
                ),
                TaskAuthRequirementMetadata(kind="ROLE", ref="role:admin"),
                TaskAuthRequirementMetadata(kind="SCOPE", ref="documents:read"),
            )
        ),
        snapshot_verifier=SnapshotVerifier(),
        authorization_policy_evaluator=PolicyEvaluator(),
        permission_checker=PermissionChecker(),
        relation_checker=RelationChecker(),
        role_checker=RoleChecker(),
        scope_checker=ScopeChecker(),
    )

    application_context.set_context_value.assert_called_once_with(
        AUTH_CONTEXT_CONTEXT_KEY,
        _auth_context(),
    )


@pytest.mark.parametrize(
    "requirement",
    [
        TaskAuthRequirementMetadata(kind="PERMISSION", ref="documents:read"),
        TaskAuthRequirementMetadata(kind="POLICY", ref="policy"),
        TaskAuthRequirementMetadata(kind="RELATION", ref="owner"),
        TaskAuthRequirementMetadata(kind="ROLE", ref="role:admin"),
        TaskAuthRequirementMetadata(kind="SCOPE", ref="documents:read"),
        TaskAuthRequirementMetadata(kind="UNKNOWN", ref="unknown"),
    ],
)
def test_seed_auth_provider_unavailable_branches_are_error(
    requirement: TaskAuthRequirementMetadata,
) -> None:
    """provider가 없거나 metadata가 불충분한 requirement는 ERROR decision이 된다."""
    with pytest.raises(AuthRequirementDeniedError) as excinfo:
        seed_and_authorize_celery_task(
            application_context=MagicMock(),
            task_name="tasks.protected",
            headers={AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"},
            auth_metadata=TaskAuthMetadata(requirements=(requirement,)),
            snapshot_verifier=SnapshotVerifier(),
            authorization_policy_evaluator=None,
            permission_checker=None,
            relation_checker=None,
            role_checker=None,
            scope_checker=None,
        )

    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state is AuthorizationDecisionState.ERROR


def test_retryable_auth_failure_requires_error_decision() -> None:
    """Celery retry는 ERROR decision이 있는 AuthRequirementDeniedError에만 적용된다."""
    assert is_retryable_auth_failure(AuthRequirementDeniedError()) is False
    assert (
        is_retryable_auth_failure(
            AuthRequirementDeniedError(
                AuthorizationDecision.challenge(
                    reason_code=AuthorizationReasonCode.SNAPSHOT_MISSING
                )
            )
        )
        is False
    )
    assert (
        is_retryable_auth_failure(
            AuthRequirementDeniedError(
                AuthorizationDecision.error(
                    reason_code=AuthorizationReasonCode.INTERNAL_ERROR
                )
            )
        )
        is True
    )
