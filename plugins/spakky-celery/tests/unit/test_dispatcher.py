"""Tests for CeleryTaskDispatchAspect and AsyncCeleryTaskDispatchAspect."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from spakky.auth import (
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthContextSnapshot,
    AuthContextSnapshotSignature,
    AuthRequirementDeniedError,
    AuthSnapshotPropagationConfig,
    AuthSubject,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    IAuthContextSnapshotSigner,
    IScopeChecker,
    ScopeCheckRequest,
    SnapshotSignRequest,
    require_auth_context,
    require_scope,
    store_auth_context,
)
from spakky.auth.aspects.authorization import AuthorizationAspect
from spakky.core.aop.advisor import Advisor
from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.order import Order
from spakky.task.stereotype.task_handler import TaskRoute
from spakky.tracing.context import TraceContext
from spakky.tracing.w3c_propagator import W3CTracePropagator
from typing import override

from spakky.plugins.celery.aspects.task_dispatch import (
    CELERY_TASK_CONTEXT_KEY,
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.common.task_result import CeleryTaskResult

# Test constants for task naming
TEST_MODULE = "test_module"
TEST_HANDLER_CLASS = "TestHandler"

SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"


def _make_task_name(method_name: str) -> str:
    """Creates fully qualified task name for test assertions."""
    return f"{TEST_MODULE}.{TEST_HANDLER_CLASS}.{method_name}"


# ── Fixtures ──


def _create_mock_celery() -> MagicMock:
    """Celery mock을 생성한다."""
    celery = MagicMock()
    celery.send_task = MagicMock()
    return celery


def _create_mock_application_context(*, inside_task: bool = False) -> MagicMock:
    """IApplicationContext mock을 생성한다."""
    context = MagicMock()
    context.get_context_value.return_value = True if inside_task else None
    return context


class ConfigurableScopeChecker(IScopeChecker):
    decision: AuthorizationDecision

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.decision = decision

    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        return self.decision


class RecordingSnapshotSigner(IAuthContextSnapshotSigner):
    requests: list[SnapshotSignRequest]

    def __init__(self) -> None:
        self.requests = []

    @override
    def sign_snapshot(self, request: SnapshotSignRequest) -> AuthContextSnapshot:
        self.requests.append(request)
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
            tenant=request.auth_context.tenant,
            roles=request.auth_context.roles,
            scopes=request.auth_context.scopes,
        )


def _create_direct_task_context() -> ApplicationContext:
    context = ApplicationContext()
    context.set_context_value(CELERY_TASK_CONTEXT_KEY, True)
    store_auth_context(
        context,
        AuthContext(
            subject=AuthSubject(id="subject-1"),
            issuer="issuer-1",
        ),
    )
    return context


def _auth_context() -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id="subject-1"),
        issuer="issuer-1",
        scopes=("tasks:run",),
    )


def _run_sync_task_aspect_chain(
    application_context: ApplicationContext,
    joinpoint: Callable[..., Any],
    authorization_decision: AuthorizationDecision,
) -> tuple[object, MagicMock]:
    celery = _create_mock_celery()
    dispatch_aspect = CeleryTaskDispatchAspect(celery)
    dispatch_aspect.set_application_context(application_context)
    auth_aspect = AuthorizationAspect(
        application_context,
        scope_checker=ConfigurableScopeChecker(authorization_decision),
    )
    runnable: Callable[..., Any] = joinpoint
    for aspect in sorted(
        (auth_aspect, dispatch_aspect),
        key=lambda item: Order.get_or_default(item, Order()).order,
        reverse=True,
    ):
        runnable = Advisor(aspect, runnable)
    return runnable(), celery


def _create_joinpoint(
    name: str,
    *,
    return_value: Any = None,  # noqa: ANN401
) -> Callable[..., Any]:
    """task name과 TaskRoute 어노테이션이 설정된 joinpoint mock을 생성한다."""

    def joinpoint(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return return_value

    joinpoint.__name__ = name
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.{name}"
    TaskRoute()(joinpoint)
    return joinpoint


# ── Sync CeleryTaskDispatchAspect ──


def test_around_dispatches_task_via_send_task() -> None:
    """CeleryTaskDispatchAspect.around이 send_task()를 호출하는지 검증한다."""
    celery = _create_mock_celery()
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_joinpoint("send_email")

    mock_async_result = MagicMock()
    mock_async_result.id = "task-abc-123"
    celery.send_task.return_value = mock_async_result

    result = aspect.around(joinpoint, to="test@example.com", subject="Hi")

    celery.send_task.assert_called_once_with(
        _make_task_name("send_email"),
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
        headers={},
    )
    assert isinstance(result, CeleryTaskResult)
    assert result.task_id == "task-abc-123"


def test_around_dispatches_task_with_positional_args() -> None:
    """CeleryTaskDispatchAspect.around이 positional args를 올바르게 전달하는지 검증한다."""
    celery = _create_mock_celery()
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_joinpoint("send_email")

    aspect.around(joinpoint, "test@example.com", "Hi")

    celery.send_task.assert_called_once_with(
        _make_task_name("send_email"),
        args=("test@example.com", "Hi"),
        kwargs={},
        headers={},
    )


def test_around_in_celery_task_context_calls_joinpoint() -> None:
    """CeleryTaskDispatchAspect.around이 Celery 태스크 컨텍스트 내에서 joinpoint를 직접 호출하는지 검증한다."""
    celery = _create_mock_celery()
    app_context = _create_mock_application_context(inside_task=True)
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(app_context)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def joinpoint(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "direct"

    joinpoint.__name__ = "send_email"
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.send_email"
    TaskRoute()(joinpoint)

    result = aspect.around(joinpoint, to="test@example.com")

    app_context.get_context_value.assert_called_once_with(CELERY_TASK_CONTEXT_KEY)
    assert calls == [((), {"to": "test@example.com"})]
    celery.send_task.assert_not_called()
    assert result == "direct"


def test_around_injects_traceparent_expect_headers_contain_traceparent() -> None:
    """propagator가 설정된 경우 send_task()에 traceparent 헤더가 포함되는지 검증한다."""
    celery = _create_mock_celery()
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    aspect.set_propagator(W3CTracePropagator())
    joinpoint = _create_joinpoint("send_email")

    ctx = TraceContext.from_traceparent(SAMPLE_TRACEPARENT)
    TraceContext.set(ctx)
    try:
        aspect.around(joinpoint)
    finally:
        TraceContext.clear()

    call_kwargs = celery.send_task.call_args
    headers = call_kwargs.kwargs["headers"]
    assert "traceparent" in headers
    assert headers["traceparent"] == SAMPLE_TRACEPARENT


def test_around_injects_signed_auth_snapshot_expect_header() -> None:
    """snapshot propagation enabled이면 signed AuthContextSnapshot이 task header로 전파된다."""
    celery = _create_mock_celery()
    signer = RecordingSnapshotSigner()
    application_context = ApplicationContext()
    store_auth_context(application_context, _auth_context())
    aspect = CeleryTaskDispatchAspect(
        celery,
        auth_snapshot_signer=signer,
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    aspect.set_application_context(application_context)
    joinpoint = _create_joinpoint("send_email")

    aspect.around(joinpoint)

    call_kwargs = celery.send_task.call_args
    headers = call_kwargs.kwargs["headers"]
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
    assert len(signer.requests) == 1
    assert signer.requests[0].auth_context == _auth_context()


def test_around_sends_empty_headers_when_propagator_none_expect_no_traceparent() -> (
    None
):
    """propagator가 None인 경우 send_task()에 빈 headers가 전달되는지 검증한다."""
    celery = _create_mock_celery()
    aspect = CeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_joinpoint("send_email")

    aspect.around(joinpoint)

    call_kwargs = celery.send_task.call_args
    assert call_kwargs.kwargs["headers"] == {}


def test_task_dispatch_aspect_runs_inside_authorization_aspect() -> None:
    """Auth enforcement must wrap direct task execution before dispatch semantics."""
    assert Order.get(AuthorizationAspect).order == 0
    assert Order.get(CeleryTaskDispatchAspect).order == 10


def test_protected_direct_task_uses_existing_auth_context() -> None:
    """같은 process task 직접 실행은 snapshot 없이 기존 AuthContext를 사용한다."""
    application_context = _create_direct_task_context()

    @TaskRoute()
    @require_scope("tasks:run")
    def joinpoint() -> str:
        return require_auth_context(application_context).subject.id

    result, celery = _run_sync_task_aspect_chain(
        application_context,
        joinpoint,
        AuthorizationDecision.allow(),
    )

    assert result == "subject-1"
    celery.send_task.assert_not_called()


@pytest.mark.parametrize(
    "decision",
    [
        AuthorizationDecision.challenge(AuthorizationReasonCode.MISSING_CREDENTIAL),
        AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_SCOPE),
        AuthorizationDecision.error(AuthorizationReasonCode.INTERNAL_ERROR),
    ],
)
def test_protected_direct_task_non_allow_decision_fails_closed(
    decision: AuthorizationDecision,
) -> None:
    """보호된 direct task는 CHALLENGE/DENY/ERROR 결정을 fail-closed 처리한다."""
    application_context = _create_direct_task_context()
    called = False

    @TaskRoute()
    @require_scope("tasks:run")
    def joinpoint() -> None:
        nonlocal called
        called = True

    with pytest.raises(AuthRequirementDeniedError) as excinfo:
        _run_sync_task_aspect_chain(application_context, joinpoint, decision)

    assert excinfo.value.decision is decision
    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state in {
        AuthorizationDecisionState.CHALLENGE,
        AuthorizationDecisionState.DENY,
        AuthorizationDecisionState.ERROR,
    }
    assert not called


# ── Async AsyncCeleryTaskDispatchAspect ──


def _create_async_joinpoint(
    name: str,
    *,
    return_value: Any = None,  # noqa: ANN401
) -> Callable[..., Awaitable[Any]]:
    """task name과 TaskRoute 어노테이션이 설정된 async joinpoint mock을 생성한다."""

    async def joinpoint(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return return_value

    joinpoint.__name__ = name
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.{name}"
    TaskRoute()(joinpoint)
    return joinpoint


@pytest.mark.asyncio
async def test_async_around_dispatches_task_via_send_task() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 send_task()를 호출하는지 검증한다."""
    celery = _create_mock_celery()
    aspect = AsyncCeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_async_joinpoint("async_send_email")

    mock_async_result = MagicMock()
    mock_async_result.id = "task-async-456"
    celery.send_task.return_value = mock_async_result

    result = await aspect.around_async(joinpoint, to="test@example.com", subject="Hi")

    celery.send_task.assert_called_once_with(
        _make_task_name("async_send_email"),
        args=(),
        kwargs={"to": "test@example.com", "subject": "Hi"},
        headers={},
    )
    assert isinstance(result, CeleryTaskResult)
    assert result.task_id == "task-async-456"


@pytest.mark.asyncio
async def test_async_around_in_celery_task_context_calls_joinpoint() -> None:
    """AsyncCeleryTaskDispatchAspect.around_async이 Celery 태스크 컨텍스트 내에서 joinpoint를 직접 호출하는지 검증한다."""
    celery = _create_mock_celery()
    app_context = _create_mock_application_context(inside_task=True)
    aspect = AsyncCeleryTaskDispatchAspect(celery)
    aspect.set_application_context(app_context)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def joinpoint(*args: Any, **kwargs: Any) -> str:
        calls.append((args, kwargs))
        return "direct"

    joinpoint.__name__ = "async_send_email"
    joinpoint.__module__ = TEST_MODULE
    joinpoint.__qualname__ = f"{TEST_HANDLER_CLASS}.async_send_email"
    TaskRoute()(joinpoint)

    result = await aspect.around_async(joinpoint, to="test@example.com")

    app_context.get_context_value.assert_called_once_with(CELERY_TASK_CONTEXT_KEY)
    assert calls == [((), {"to": "test@example.com"})]
    celery.send_task.assert_not_called()
    assert result == "direct"


@pytest.mark.asyncio
async def test_async_around_injects_traceparent_expect_headers_contain_traceparent() -> (
    None
):
    """async propagator가 설정된 경우 send_task()에 traceparent 헤더가 포함되는지 검증한다."""
    celery = _create_mock_celery()
    aspect = AsyncCeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    aspect.set_propagator(W3CTracePropagator())
    joinpoint = _create_async_joinpoint("async_send_email")

    ctx = TraceContext.from_traceparent(SAMPLE_TRACEPARENT)
    TraceContext.set(ctx)
    try:
        await aspect.around_async(joinpoint)
    finally:
        TraceContext.clear()

    call_kwargs = celery.send_task.call_args
    headers = call_kwargs.kwargs["headers"]
    assert "traceparent" in headers
    assert headers["traceparent"] == SAMPLE_TRACEPARENT


@pytest.mark.asyncio
async def test_async_around_injects_signed_auth_snapshot_expect_header() -> None:
    """async dispatch도 signed AuthContextSnapshot을 task header로 전파한다."""
    celery = _create_mock_celery()
    signer = RecordingSnapshotSigner()
    application_context = ApplicationContext()
    store_auth_context(application_context, _auth_context())
    aspect = AsyncCeleryTaskDispatchAspect(
        celery,
        auth_snapshot_signer=signer,
        auth_snapshot_propagation_config=AuthSnapshotPropagationConfig(enabled=True),
    )
    aspect.set_application_context(application_context)
    joinpoint = _create_async_joinpoint("async_send_email")

    await aspect.around_async(joinpoint)

    call_kwargs = celery.send_task.call_args
    headers = call_kwargs.kwargs["headers"]
    assert AUTH_CONTEXT_SNAPSHOT_METADATA_KEY in headers
    assert len(signer.requests) == 1
    assert signer.requests[0].auth_context == _auth_context()


@pytest.mark.asyncio
async def test_async_around_sends_empty_headers_when_propagator_none_expect_no_traceparent() -> (
    None
):
    """async propagator가 None인 경우 send_task()에 빈 headers가 전달되는지 검증한다."""
    celery = _create_mock_celery()
    aspect = AsyncCeleryTaskDispatchAspect(celery)
    aspect.set_application_context(_create_mock_application_context())
    joinpoint = _create_async_joinpoint("async_send_email")

    await aspect.around_async(joinpoint)

    call_kwargs = celery.send_task.call_args
    assert call_kwargs.kwargs["headers"] == {}
