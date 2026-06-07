"""Unit tests for saga AuthContextSnapshot propagation and protected steps."""

from dataclasses import replace
from typing import override
from uuid import UUID, uuid4

import pytest

from spakky.auth import (
    AuthContext,
    AuthInvocation,
    AuthRequirementDeniedError,
    AuthSubject,
    AuthorizationRequest,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    AuthVerificationProviderUnavailableError,
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
    protected,
    require_permission,
    require_policy,
    require_relation,
    require_role,
    require_scope,
)
from spakky.core.common.mutability import immutable
from spakky.saga import (
    AbstractSaga,
    AbstractSagaData,
    SagaAuthExecutionContext,
    SagaFlow,
    SagaResult,
    SagaStatus,
    StepStatus,
    parallel,
    saga_flow,
    saga_step,
    step,
)


@immutable
class _AuthSagaData(AbstractSagaData):
    order_id: UUID
    marker: str | None = None


class _SnapshotVerifier(IAuthContextSnapshotVerifier):
    invocations: list[AuthInvocation]
    error: Exception | None

    def __init__(self, error: Exception | None = None) -> None:
        self.invocations = []
        self.error = error

    @override
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        self.invocations.append(invocation)
        if self.error is not None:
            raise self.error
        return AuthContext(
            subject=AuthSubject(id=snapshot_envelope),
            issuer="unit-test",
            scopes=("orders:write",),
        )


class _ScopeChecker(IScopeChecker):
    decision: AuthorizationDecision

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.decision = decision

    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        return self.decision


class _PermissionChecker(IPermissionChecker):
    @override
    def check_permission(
        self, request: PermissionCheckRequest
    ) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class _PolicyEvaluator(IAuthorizationPolicyEvaluator):
    @override
    def evaluate_policy(self, request: AuthorizationRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class _RelationChecker(IRelationChecker):
    @override
    def check_relation(self, request: RelationCheckRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


class _RoleChecker(IRoleChecker):
    @override
    def check_role(self, request: RoleCheckRequest) -> AuthorizationDecision:
        return AuthorizationDecision.allow()


async def _succeed(data: _AuthSagaData) -> None:
    """Successful saga step."""


async def _replace_without_snapshot(data: _AuthSagaData) -> _AuthSagaData:
    return replace(data, marker="replaced", auth_context_snapshot=None)


async def _replace_with_new_snapshot(data: _AuthSagaData) -> _AuthSagaData:
    return replace(data, marker="replaced", auth_context_snapshot="new-snapshot")


async def _fail(data: _AuthSagaData) -> None:
    raise RuntimeError("step failed")


async def _compensate_logged(data: _AuthSagaData) -> None:
    _compensation_log.append(data.auth_context_snapshot or "missing")


@protected
async def _protected_step(data: _AuthSagaData) -> None:
    """Standalone protected step."""


@protected
async def _protected_compensate(data: _AuthSagaData) -> None:
    _compensation_log.append(data.auth_context_snapshot or "missing")


@require_scope("orders:write")
async def _scope_protected_step(data: _AuthSagaData) -> None:
    """Scope-protected standalone step."""


@require_permission("orders:create", resource="order", tenant="tenant-a")
async def _permission_protected_step(data: _AuthSagaData) -> None:
    """Permission-protected standalone step."""


@require_policy("order", "create", tenant="tenant-a")
async def _policy_protected_step(data: _AuthSagaData) -> None:
    """Policy-protected standalone step."""


@require_relation("owner", resource="order:1", tenant="tenant-a")
async def _relation_protected_step(data: _AuthSagaData) -> None:
    """Relation-protected standalone step."""


@require_role("admin", tenant="tenant-a")
async def _role_protected_step(data: _AuthSagaData) -> None:
    """Role-protected standalone step."""


_compensation_log: list[str] = []


@pytest.fixture(autouse=True)
def _clear_compensation_log() -> None:
    _compensation_log.clear()


def _data(snapshot: str | None = "signed-snapshot") -> _AuthSagaData:
    return _AuthSagaData(order_id=uuid4(), auth_context_snapshot=snapshot)


def _auth_context(
    verifier: IAuthContextSnapshotVerifier | None = None,
    scope_checker: IScopeChecker | None = None,
) -> SagaAuthExecutionContext:
    return SagaAuthExecutionContext(
        snapshot_verifier=verifier,
        scope_checker=scope_checker,
    )


def _denied_error(result_error: Exception | None) -> AuthRequirementDeniedError:
    assert isinstance(result_error, AuthRequirementDeniedError)
    return result_error


def _assert_error_decision(
    result_error: Exception | None,
    state: AuthorizationDecisionState,
) -> None:
    error = _denied_error(result_error)
    assert error.decision is not None
    assert error.decision.state is state


@pytest.mark.asyncio
async def test_data_replacement_preserves_auth_context_snapshot() -> None:
    """SagaData replacement carries the existing snapshot envelope forward."""
    flow = saga_flow(step(_replace_without_snapshot))
    result = await saga_flow_run(flow, _data("snapshot-1"))

    assert result.status is SagaStatus.COMPLETED
    assert result.data.marker == "replaced"
    assert result.data.auth_context_snapshot == "snapshot-1"


@pytest.mark.asyncio
async def test_data_replacement_with_new_snapshot_keeps_returned_snapshot() -> None:
    """SagaData replacement can intentionally rotate the snapshot envelope."""
    flow = saga_flow(step(_replace_with_new_snapshot))
    result = await saga_flow_run(flow, _data("old-snapshot"))

    assert result.status is SagaStatus.COMPLETED
    assert result.data.auth_context_snapshot == "new-snapshot"


@pytest.mark.asyncio
async def test_protected_metadata_survives_saga_step_descriptor_conversion() -> None:
    """@saga_step wrapping preserves protected metadata on the original method."""

    class ProtectedSaga(AbstractSaga[_AuthSagaData]):
        @saga_step
        @protected
        async def protected_method(self, data: _AuthSagaData) -> None:
            """Protected saga step."""

        def flow(self) -> SagaFlow[_AuthSagaData]:
            return saga_flow(self.protected_method)

    verifier = _SnapshotVerifier()
    result = await ProtectedSaga().execute(
        _data("subject-1"),
        auth_context=_auth_context(verifier),
    )

    assert result.status is SagaStatus.COMPLETED
    assert [invocation.operation for invocation in verifier.invocations] == [
        "protected_method"
    ]


@pytest.mark.asyncio
async def test_protected_metadata_on_descriptor_survives_instance_access() -> None:
    """@protected applied outside @saga_step remains visible after descriptor access."""

    class ProtectedSaga(AbstractSaga[_AuthSagaData]):
        @protected
        @saga_step
        async def protected_method(self, data: _AuthSagaData) -> None:
            """Protected saga step."""

        def flow(self) -> SagaFlow[_AuthSagaData]:
            return saga_flow(self.protected_method)

    verifier = _SnapshotVerifier()
    result = await ProtectedSaga().execute(
        _data("subject-1"),
        auth_context=_auth_context(verifier),
    )

    assert result.status is SagaStatus.COMPLETED
    assert len(verifier.invocations) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot", "verifier", "reason_code"),
    [
        (None, _SnapshotVerifier(), AuthorizationReasonCode.SNAPSHOT_MISSING),
        ("", _SnapshotVerifier(), AuthorizationReasonCode.SNAPSHOT_MISSING),
        (
            "missing",
            _SnapshotVerifier(MissingAuthContextSnapshotError()),
            AuthorizationReasonCode.SNAPSHOT_MISSING,
        ),
        (
            "invalid",
            _SnapshotVerifier(InvalidAuthContextSnapshotError()),
            AuthorizationReasonCode.SNAPSHOT_INVALID,
        ),
        (
            "expired",
            _SnapshotVerifier(ExpiredAuthContextSnapshotError()),
            AuthorizationReasonCode.SNAPSHOT_EXPIRED,
        ),
    ],
)
async def test_protected_step_snapshot_challenge_failures(
    snapshot: str | None,
    verifier: _SnapshotVerifier,
    reason_code: AuthorizationReasonCode,
) -> None:
    """Missing, invalid, and expired snapshots fail protected steps as CHALLENGE."""
    result = await saga_flow_run(
        saga_flow(step(_protected_step)),
        _data(snapshot),
        auth_context=_auth_context(verifier),
    )

    error = _denied_error(result.error)
    assert result.status is SagaStatus.FAILED
    assert result.failed_step == "_protected_step"
    assert error.decision is not None
    assert error.decision.state is AuthorizationDecisionState.CHALLENGE
    assert error.decision.reason_code is reason_code


@pytest.mark.asyncio
async def test_protected_step_without_verifier_expect_error_failure() -> None:
    """Protected snapshot verification without a provider fails as ERROR."""
    result = await saga_flow_run(
        saga_flow(step(_protected_step)),
        _data(),
        auth_context=_auth_context(),
    )

    assert result.status is SagaStatus.FAILED
    _assert_error_decision(result.error, AuthorizationDecisionState.ERROR)


@pytest.mark.asyncio
async def test_scope_deny_expect_step_failure() -> None:
    """DENY decisions from protected requirements fail the saga step."""
    result = await saga_flow_run(
        saga_flow(step(_scope_protected_step)),
        _data(),
        auth_context=_auth_context(
            _SnapshotVerifier(),
            _ScopeChecker(
                AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_SCOPE)
            ),
        ),
    )

    error = _denied_error(result.error)
    assert result.status is SagaStatus.FAILED
    assert error.decision is not None
    assert error.decision.state is AuthorizationDecisionState.DENY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("protected_step", "auth_context"),
    [
        (
            _permission_protected_step,
            SagaAuthExecutionContext(
                snapshot_verifier=_SnapshotVerifier(),
                permission_checker=_PermissionChecker(),
            ),
        ),
        (
            _policy_protected_step,
            SagaAuthExecutionContext(
                snapshot_verifier=_SnapshotVerifier(),
                authorization_policy_evaluator=_PolicyEvaluator(),
            ),
        ),
        (
            _relation_protected_step,
            SagaAuthExecutionContext(
                snapshot_verifier=_SnapshotVerifier(),
                relation_checker=_RelationChecker(),
            ),
        ),
        (
            _role_protected_step,
            SagaAuthExecutionContext(
                snapshot_verifier=_SnapshotVerifier(),
                role_checker=_RoleChecker(),
            ),
        ),
    ],
)
async def test_protected_requirement_provider_allow_paths_complete(
    protected_step,
    auth_context: SagaAuthExecutionContext,
) -> None:
    """Permission, policy, relation, and role provider ALLOW paths complete."""
    result = await saga_flow_run(
        saga_flow(step(protected_step)),
        _data(),
        auth_context=auth_context,
    )

    assert result.status is SagaStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protected_step",
    [
        _permission_protected_step,
        _policy_protected_step,
        _relation_protected_step,
        _role_protected_step,
        _scope_protected_step,
    ],
)
async def test_missing_requirement_provider_expect_error_failure(
    protected_step,
) -> None:
    """Missing checker/evaluator providers fail protected requirements as ERROR."""
    result = await saga_flow_run(
        saga_flow(step(protected_step)),
        _data(),
        auth_context=_auth_context(_SnapshotVerifier()),
    )

    assert result.status is SagaStatus.FAILED
    _assert_error_decision(result.error, AuthorizationDecisionState.ERROR)


@pytest.mark.asyncio
async def test_verification_provider_unavailable_compensates_committed_steps() -> None:
    """Provider ERROR decisions follow existing failure and compensation policy."""
    result = await saga_flow_run(
        saga_flow(
            step(_succeed, compensate=_compensate_logged),
            step(_protected_step),
        ),
        _data("subject-1"),
        auth_context=_auth_context(
            _SnapshotVerifier(AuthVerificationProviderUnavailableError())
        ),
    )

    error = _denied_error(result.error)
    assert result.status is SagaStatus.FAILED
    assert error.decision is not None
    assert error.decision.state is AuthorizationDecisionState.ERROR
    assert _compensation_log == ["subject-1"]
    assert result.history[-1].status is StepStatus.COMPENSATED


@pytest.mark.asyncio
async def test_protected_compensation_uses_carried_snapshot() -> None:
    """Protected compensation verifies with the same propagated snapshot envelope."""
    verifier = _SnapshotVerifier()
    result = await saga_flow_run(
        saga_flow(
            step(_succeed, compensate=_protected_compensate),
            step(_fail),
        ),
        _data("compensating-subject"),
        auth_context=_auth_context(verifier),
    )

    assert result.status is SagaStatus.FAILED
    assert _compensation_log == ["compensating-subject"]
    assert [invocation.operation for invocation in verifier.invocations] == ["_succeed"]


@pytest.mark.asyncio
async def test_parallel_protected_steps_share_snapshot_semantics() -> None:
    """Parallel protected steps verify against the same carried snapshot envelope."""
    verifier = _SnapshotVerifier()
    result = await saga_flow_run(
        saga_flow(parallel(_protected_step, _protected_step)),
        _data("parallel-subject"),
        auth_context=_auth_context(verifier),
    )

    assert result.status is SagaStatus.COMPLETED
    assert result.data.auth_context_snapshot == "parallel-subject"
    assert [invocation.operation for invocation in verifier.invocations] == [
        "_protected_step",
        "_protected_step",
    ]


async def saga_flow_run(
    flow: SagaFlow[_AuthSagaData],
    data: _AuthSagaData,
    *,
    auth_context: SagaAuthExecutionContext | None = None,
) -> SagaResult[_AuthSagaData]:
    from spakky.saga import run_saga_flow

    return await run_saga_flow(flow, data, auth_context=auth_context)
