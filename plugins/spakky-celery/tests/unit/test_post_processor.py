"""Tests for CeleryPostProcessor."""

from collections.abc import Callable
from datetime import time, timedelta
from typing import override
from unittest.mock import MagicMock, patch

import pytest
from celery import Celery
from celery.exceptions import Retry
from celery.schedules import crontab as celery_crontab
from celery.schedules import schedule as celery_schedule
from spakky.auth import (
    AUTH_CONTEXT_CONTEXT_KEY,
    AUTH_CONTEXT_SNAPSHOT_METADATA_KEY,
    AuthContext,
    AuthInvocation,
    AuthRequirementDeniedError,
    AuthSubject,
    AuthVerificationProviderUnavailableError,
    AuthorizationDecision,
    AuthorizationDecisionState,
    AuthorizationReasonCode,
    ExpiredAuthContextSnapshotError,
    IAuthContextSnapshotVerifier,
    IScopeChecker,
    InvalidAuthContextSnapshotError,
    ScopeCheckRequest,
    require_scope,
)
from spakky.core.utils.inspection import get_fully_qualified_name
from spakky.task.stereotype.crontab import Crontab, Weekday
from spakky.task.stereotype.schedule import schedule
from spakky.task.stereotype.task_handler import TaskHandler, task
from spakky.tracing.context import TraceContext
from spakky.tracing.propagator import ITracePropagator
from spakky.tracing.w3c_propagator import W3CTracePropagator

from spakky.plugins.celery.aspects.task_dispatch import (
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.post_processor import CeleryPostProcessor


@TaskHandler()
class _SampleTaskHandler:
    @task
    def send_email(self, to: str, subject: str) -> None:
        pass

    @task
    def process_data(self, data: str) -> None:
        pass


def _auth_context() -> AuthContext:
    return AuthContext(
        subject=AuthSubject(id="subject-1"),
        issuer="issuer-1",
        scopes=("tasks:run",),
    )


class SnapshotVerifier(IAuthContextSnapshotVerifier):
    error: Exception | None
    calls: list[tuple[str, AuthInvocation]]

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    @override
    def verify_snapshot(
        self,
        snapshot_envelope: str,
        invocation: AuthInvocation,
    ) -> AuthContext:
        self.calls.append((snapshot_envelope, invocation))
        if self.error is not None:
            raise self.error
        return _auth_context()


class ScopeChecker(IScopeChecker):
    decision: AuthorizationDecision
    requests: list[ScopeCheckRequest]

    def __init__(self, decision: AuthorizationDecision) -> None:
        self.decision = decision
        self.requests = []

    @override
    def check_scope(self, request: ScopeCheckRequest) -> AuthorizationDecision:
        self.requests.append(request)
        return self.decision


def _create_celery() -> Celery:
    """테스트용 Celery를 생성한다."""
    return Celery(main="test", broker="memory://")


def _create_post_processor(celery: Celery) -> CeleryPostProcessor:
    """CeleryPostProcessor를 생성하고 Aware 인터페이스를 설정한다."""
    context_mock = MagicMock()
    context_mock.get.return_value = celery
    context_mock.get_or_none.return_value = None

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(context_mock)
    return post_processor


def test_celery_post_processor_registers_tasks_on_post_process() -> None:
    """CeleryPostProcessor가 post_process()에서 @task 메서드를 Celery 태스크로 등록하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    handler = _SampleTaskHandler()

    post_processor.post_process(handler)

    registered_tasks = list(celery.tasks.keys())
    # Use specific prefix to avoid matching tasks from other test modules
    sample_handler_prefix = "tests.unit.test_post_processor._SampleTaskHandler"
    send_email_tasks = [
        t for t in registered_tasks if t == f"{sample_handler_prefix}.send_email"
    ]
    process_data_tasks = [
        t for t in registered_tasks if t == f"{sample_handler_prefix}.process_data"
    ]

    assert len(send_email_tasks) == 1
    assert len(process_data_tasks) == 1


def test_celery_post_processor_collects_task_routes() -> None:
    """CeleryPostProcessor가 post_process()에서 태스크를 Celery에 등록하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    handler = _SampleTaskHandler()

    post_processor.post_process(handler)

    sample_handler_prefix = "tests.unit.test_post_processor._SampleTaskHandler"
    assert f"{sample_handler_prefix}.send_email" in celery.tasks
    assert f"{sample_handler_prefix}.process_data" in celery.tasks


def test_celery_post_processor_ignores_non_task_handler_pods() -> None:
    """CeleryPostProcessor가 @TaskHandler가 아닌 Pod를 무시하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    initial_task_count = len(celery.tasks)

    class NotATaskHandler:
        def some_method(self) -> None:
            pass

    result = post_processor.post_process(NotATaskHandler())

    assert isinstance(result, NotATaskHandler)
    assert len(celery.tasks) == initial_task_count


def test_celery_post_processor_returns_pod() -> None:
    """CeleryPostProcessor.post_process()가 pod를 반환하는지 검증한다."""
    celery = _create_celery()
    post_processor = _create_post_processor(celery)
    handler = _SampleTaskHandler()

    result = post_processor.post_process(handler)

    assert result is handler


def test_celery_post_processor_registers_wrapper_with_context_isolation() -> None:
    """등록된 래퍼가 실행 시 컨텍스트를 비우고 컨테이너에서 핸들러를 다시 조회하는지 검증한다."""

    @TaskHandler()
    class TrackingTaskHandler:
        def __init__(self) -> None:
            self.calls: list[str] = []

        @task
        def track(self, value: str) -> str:
            self.calls.append(value)
            return value

    celery_mock = MagicMock()
    application_context_mock = MagicMock()
    tracking_handler = TrackingTaskHandler()

    def get_from_context(type_: object) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is TrackingTaskHandler:
            return tracking_handler
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context
    application_context_mock.get_or_none.return_value = None

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)

    post_processor.post_process(tracking_handler)

    # celery.task(name=task_name) returns a decorator, which is called with endpoint
    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    result = endpoint("payload")

    application_context_mock.clear_context.assert_called_once()
    assert application_context_mock.get.call_count >= 2
    assert tracking_handler.calls == ["payload"]
    assert result == "payload"


def test_celery_post_processor_registers_async_tasks() -> None:
    """CeleryPostProcessor가 async 메서드를 올바르게 등록하고 실행하는지 검증한다."""

    @TaskHandler()
    class AsyncTaskHandler:
        def __init__(self) -> None:
            self.calls: list[str] = []

        @task
        async def async_task(self, value: str) -> str:
            self.calls.append(value)
            return f"async: {value}"

    celery_mock = MagicMock()
    application_context_mock = MagicMock()
    async_handler = AsyncTaskHandler()

    def get_from_context(type_: object) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is AsyncTaskHandler:
            return async_handler
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context
    application_context_mock.get_or_none.return_value = None

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)

    post_processor.post_process(async_handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    # async endpoint는 asyncio.run()으로 실행되어야 함
    result = endpoint("async_payload")

    application_context_mock.clear_context.assert_called_once()
    assert async_handler.calls == ["async_payload"]
    assert result == "async: async_payload"


def _registered_endpoint_for_handler(
    handler_type: type[object],
    handler: object,
    *,
    snapshot_verifier: IAuthContextSnapshotVerifier | None,
    scope_checker: IScopeChecker | None,
) -> tuple[Callable[..., object], MagicMock]:
    celery_mock = MagicMock()
    application_context_mock = MagicMock()

    def get_from_context(type_: type[object]) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is handler_type:
            return handler
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context
    application_context_mock.get_or_none.return_value = None

    post_processor = CeleryPostProcessor(
        auth_snapshot_verifier=snapshot_verifier,
        scope_checker=scope_checker,
    )
    post_processor.set_application_context(application_context_mock)
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]
    return endpoint, application_context_mock


def test_protected_sync_endpoint_verifies_snapshot_and_seeds_auth_context() -> None:
    """protected worker task는 snapshot 검증 후 AuthContext를 seed하고 실행한다."""

    @TaskHandler()
    class ProtectedHandler:
        def __init__(self) -> None:
            self.calls: list[str] = []

        @task
        @require_scope("tasks:run")
        def protected_task(self, value: str) -> str:
            self.calls.append(value)
            return value

    handler = ProtectedHandler()
    verifier = SnapshotVerifier()
    checker = ScopeChecker(AuthorizationDecision.allow())
    endpoint, application_context_mock = _registered_endpoint_for_handler(
        ProtectedHandler,
        handler,
        snapshot_verifier=verifier,
        scope_checker=checker,
    )
    mock_request = MagicMock()
    mock_request.get.return_value = {
        AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"
    }

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        result = endpoint("payload")

    assert result == "payload"
    assert handler.calls == ["payload"]
    assert verifier.calls[0][0] == "snapshot-envelope"
    assert checker.requests[0].auth_context == _auth_context()
    application_context_mock.set_context_value.assert_any_call(
        AUTH_CONTEXT_CONTEXT_KEY,
        _auth_context(),
    )


@pytest.mark.parametrize(
    ("headers", "verifier_error", "expected_reason"),
    [
        ({}, None, AuthorizationReasonCode.SNAPSHOT_MISSING),
        (
            {AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "invalid-envelope"},
            InvalidAuthContextSnapshotError(),
            AuthorizationReasonCode.SNAPSHOT_INVALID,
        ),
        (
            {AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "expired-envelope"},
            ExpiredAuthContextSnapshotError(),
            AuthorizationReasonCode.SNAPSHOT_EXPIRED,
        ),
    ],
)
def test_protected_sync_endpoint_snapshot_challenge_fails_closed(
    headers: dict[str, str],
    verifier_error: Exception | None,
    expected_reason: AuthorizationReasonCode,
) -> None:
    """missing/invalid/expired snapshot은 CHALLENGE task failure로 닫힌다."""

    @TaskHandler()
    class ProtectedHandler:
        def __init__(self) -> None:
            self.called = False

        @task
        @require_scope("tasks:run")
        def protected_task(self) -> None:
            self.called = True

    handler = ProtectedHandler()
    endpoint, _ = _registered_endpoint_for_handler(
        ProtectedHandler,
        handler,
        snapshot_verifier=SnapshotVerifier(verifier_error),
        scope_checker=ScopeChecker(AuthorizationDecision.allow()),
    )
    mock_request = MagicMock()
    mock_request.get.return_value = headers

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        with pytest.raises(AuthRequirementDeniedError) as excinfo:
            endpoint()

    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state is AuthorizationDecisionState.CHALLENGE
    assert excinfo.value.decision.reason_code is expected_reason
    assert not handler.called
    mock_current_task.retry.assert_not_called()


def test_protected_sync_endpoint_deny_fails_task_without_retry() -> None:
    """authorization DENY decision은 retry 없이 task failure가 된다."""

    @TaskHandler()
    class ProtectedHandler:
        def __init__(self) -> None:
            self.called = False

        @task
        @require_scope("tasks:run")
        def protected_task(self) -> None:
            self.called = True

    handler = ProtectedHandler()
    endpoint, _ = _registered_endpoint_for_handler(
        ProtectedHandler,
        handler,
        snapshot_verifier=SnapshotVerifier(),
        scope_checker=ScopeChecker(
            AuthorizationDecision.deny(AuthorizationReasonCode.INSUFFICIENT_SCOPE)
        ),
    )
    mock_request = MagicMock()
    mock_request.get.return_value = {
        AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"
    }

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        with pytest.raises(AuthRequirementDeniedError) as excinfo:
            endpoint()

    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state is AuthorizationDecisionState.DENY
    assert not handler.called
    mock_current_task.retry.assert_not_called()


def test_protected_sync_endpoint_verification_error_uses_celery_retry() -> None:
    """verification provider unavailable ERROR는 Celery retryable task 오류로 매핑된다."""

    @TaskHandler()
    class ProtectedHandler:
        def __init__(self) -> None:
            self.called = False

        @task
        @require_scope("tasks:run")
        def protected_task(self) -> None:
            self.called = True

    handler = ProtectedHandler()
    endpoint, _ = _registered_endpoint_for_handler(
        ProtectedHandler,
        handler,
        snapshot_verifier=SnapshotVerifier(AuthVerificationProviderUnavailableError()),
        scope_checker=ScopeChecker(AuthorizationDecision.allow()),
    )
    mock_request = MagicMock()
    mock_request.get.return_value = {
        AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"
    }

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        mock_current_task.retry.side_effect = Retry()
        with pytest.raises(Retry):
            endpoint()

    retry_error = mock_current_task.retry.call_args.kwargs["exc"]
    assert isinstance(retry_error, AuthRequirementDeniedError)
    assert retry_error.decision is not None
    assert retry_error.decision.state is AuthorizationDecisionState.ERROR
    assert not handler.called


def test_protected_sync_endpoint_expect_denial_propagates_when_retry_does_not_raise() -> (
    None
):
    """celery retry가 Retry를 발생시키지 못하면 원래 auth 실패가 그대로 전파된다."""

    @TaskHandler()
    class ProtectedHandler:
        def __init__(self) -> None:
            self.called = False

        @task
        @require_scope("tasks:run")
        def protected_task(self) -> None:
            self.called = True

    handler = ProtectedHandler()
    endpoint, _ = _registered_endpoint_for_handler(
        ProtectedHandler,
        handler,
        snapshot_verifier=SnapshotVerifier(AuthVerificationProviderUnavailableError()),
        scope_checker=ScopeChecker(AuthorizationDecision.allow()),
    )
    mock_request = MagicMock()
    mock_request.get.return_value = {
        AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"
    }

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        with pytest.raises(AuthRequirementDeniedError) as excinfo:
            endpoint()

    mock_current_task.retry.assert_called_once()
    assert excinfo.value.decision is not None
    assert excinfo.value.decision.state is AuthorizationDecisionState.ERROR
    assert not handler.called


def test_schedule_only_endpoint_expect_auth_seeding_skipped() -> None:
    """@task 없이 @schedule만 붙은 beat 메서드는 auth seeding 없이 실행된다."""

    @TaskHandler()
    class ScheduleOnlyHandler:
        def __init__(self) -> None:
            self.called = False

        @schedule(interval=timedelta(minutes=5))
        def refresh_cache(self) -> None:
            self.called = True

    handler = ScheduleOnlyHandler()
    verifier = SnapshotVerifier()
    endpoint, _ = _registered_endpoint_for_handler(
        ScheduleOnlyHandler,
        handler,
        snapshot_verifier=verifier,
        scope_checker=ScopeChecker(AuthorizationDecision.allow()),
    )
    mock_request = MagicMock()
    mock_request.get.return_value = {
        AUTH_CONTEXT_SNAPSHOT_METADATA_KEY: "snapshot-envelope"
    }

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        endpoint()

    assert handler.called
    assert verifier.calls == []
    mock_current_task.retry.assert_not_called()


# =============================================================================
# Scenario: Schedule registration
# =============================================================================


def test_celery_post_processor_registers_interval_schedule() -> None:
    """CeleryPostProcessor가 @schedule(interval=...) 메서드를 beat_schedule에 등록하는지 검증한다."""

    @TaskHandler()
    class ScheduledHandler:
        @schedule(interval=timedelta(minutes=30))
        def health_check(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(ScheduledHandler())

    task_name = get_fully_qualified_name(ScheduledHandler.health_check)
    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert entry["task"] == task_name
    assert isinstance(entry["schedule"], celery_schedule)


def test_celery_post_processor_registers_at_schedule() -> None:
    """CeleryPostProcessor가 @schedule(at=...) 메서드를 beat_schedule에 crontab으로 등록하는지 검증한다."""

    @TaskHandler()
    class DailyHandler:
        @schedule(at=time(3, 0))
        def daily_cleanup(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(DailyHandler())

    task_name = get_fully_qualified_name(DailyHandler.daily_cleanup)
    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert isinstance(entry["schedule"], celery_crontab)


def test_celery_post_processor_registers_crontab_schedule() -> None:
    """CeleryPostProcessor가 @schedule(crontab=...) 메서드를 beat_schedule에 등록하는지 검증한다."""

    @TaskHandler()
    class WeeklyHandler:
        @schedule(
            crontab=Crontab(
                hour=9, weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)
            )
        )
        def triweekly_report(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(WeeklyHandler())

    task_name = get_fully_qualified_name(WeeklyHandler.triweekly_report)
    assert task_name in celery.conf.beat_schedule
    entry = celery.conf.beat_schedule[task_name]
    assert isinstance(entry["schedule"], celery_crontab)


def test_celery_post_processor_schedule_method_also_registered_as_celery_task() -> None:
    """@schedule 메서드도 Celery task로 등록되는지 검증한다."""

    @TaskHandler()
    class ScheduledHandler:
        @schedule(interval=timedelta(hours=1))
        def periodic_job(self) -> None:
            pass

    celery = _create_celery()
    post_processor = _create_post_processor(celery)

    post_processor.post_process(ScheduledHandler())

    task_name = get_fully_qualified_name(ScheduledHandler.periodic_job)
    assert task_name in celery.tasks


def test_crontab_to_celery_converts_intenum_to_numeric_string() -> None:
    """_crontab_to_celery가 IntEnum(Month, Weekday)을 숫자 문자열로 변환하는지 검증한다."""
    from spakky.task.stereotype.crontab import Month

    crontab = Crontab(
        month=Month.JANUARY,
        weekday=Weekday.MONDAY,
        hour=9,
        minute=30,
    )

    celery_cron = CeleryPostProcessor._crontab_to_celery(crontab)
    cron_dict = vars(celery_cron)

    # IntEnum이 "Month.JANUARY"가 아닌 "1"로 변환되어야 함
    assert cron_dict["_orig_month_of_year"] == "1"  # Month.JANUARY = 1
    assert cron_dict["_orig_day_of_week"] == "0"  # Weekday.MONDAY = 0


def test_crontab_to_celery_converts_tuple_of_intenum_to_numeric_string() -> None:
    """_crontab_to_celery가 IntEnum 튜플을 쉼표로 구분된 숫자 문자열로 변환하는지 검증한다."""
    from spakky.task.stereotype.crontab import Month

    crontab = Crontab(
        month=(Month.JANUARY, Month.JULY),
        weekday=(Weekday.MONDAY, Weekday.FRIDAY),
        hour=12,
    )

    celery_cron = CeleryPostProcessor._crontab_to_celery(crontab)
    cron_dict = vars(celery_cron)

    # 튜플이 "1,7"로 변환되어야 함 (Month.JANUARY=1, Month.JULY=7)
    assert cron_dict["_orig_month_of_year"] == "1,7"
    # Weekday.MONDAY=0, Weekday.FRIDAY=4
    assert cron_dict["_orig_day_of_week"] == "0,4"


# =============================================================================
# Scenario: Trace context propagation
# =============================================================================

SAMPLE_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
SAMPLE_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"
SAMPLE_SPAN_ID = "b7ad6b7169203331"


def _create_tracing_post_processor(
    celery_mock: MagicMock,
    handler_type: type[object],
    handler_instance: object,
    *,
    with_propagator: bool = True,
) -> CeleryPostProcessor:
    """트레이싱 테스트용 CeleryPostProcessor를 생성한다."""

    propagator = W3CTracePropagator()
    sync_aspect = CeleryTaskDispatchAspect(celery_mock)
    async_aspect = AsyncCeleryTaskDispatchAspect(celery_mock)

    application_context_mock = MagicMock()

    def get_from_context(type_: type[object]) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is handler_type:
            return handler_instance
        if type_ is ITracePropagator:
            return propagator
        if type_ is CeleryTaskDispatchAspect:
            return sync_aspect
        if type_ is AsyncCeleryTaskDispatchAspect:
            return async_aspect
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context
    application_context_mock.get_or_none.return_value = (
        propagator if with_propagator else None
    )
    application_context_mock.contains.return_value = with_propagator

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)
    return post_processor


def test_sync_endpoint_extracts_trace_context_expect_child_span() -> None:
    """sync 엔드포인트가 traceparent 헤더에서 trace context를 추출하여 child span을 생성하는지 검증한다."""

    @TaskHandler()
    class TracingHandler:
        def __init__(self) -> None:
            self.captured_ctx: TraceContext | None = None

        @task
        def traced_task(self) -> None:
            self.captured_ctx = TraceContext.get()

    handler = TracingHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, TracingHandler, handler
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    mock_request = MagicMock()
    mock_request.get.return_value = {"traceparent": SAMPLE_TRACEPARENT}
    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        endpoint()

    assert handler.captured_ctx is not None
    assert handler.captured_ctx.trace_id == SAMPLE_TRACE_ID
    assert handler.captured_ctx.parent_span_id == SAMPLE_SPAN_ID
    assert handler.captured_ctx.span_id != SAMPLE_SPAN_ID
    assert TraceContext.get() is None


def test_sync_endpoint_creates_root_when_no_traceparent_expect_new_root() -> None:
    """sync 엔드포인트에서 traceparent 헤더가 없을 때 새 root trace를 생성하는지 검증한다."""

    @TaskHandler()
    class RootTraceHandler:
        def __init__(self) -> None:
            self.captured_ctx: TraceContext | None = None

        @task
        def traced_task(self) -> None:
            self.captured_ctx = TraceContext.get()

    handler = RootTraceHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, RootTraceHandler, handler
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    mock_request = MagicMock()
    mock_request.get.return_value = {}
    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        endpoint()

    assert handler.captured_ctx is not None
    assert handler.captured_ctx.parent_span_id is None
    assert TraceContext.get() is None


def test_sync_endpoint_clears_trace_context_on_exception_expect_none() -> None:
    """sync 엔드포인트에서 핸들러가 예외를 발생시켜도 TraceContext가 정리되는지 검증한다."""

    @TaskHandler()
    class FailingHandler:
        @task
        def failing_task(self) -> None:
            raise RuntimeError("boom")

    handler = FailingHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, FailingHandler, handler
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    mock_request = MagicMock()
    mock_request.get.return_value = {"traceparent": SAMPLE_TRACEPARENT}

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        with pytest.raises(RuntimeError, match="boom"):
            endpoint()

    assert TraceContext.get() is None


def test_sync_endpoint_no_trace_when_propagator_none_expect_context_unset() -> None:
    """propagator가 없을 때 sync 엔드포인트에서 TraceContext가 설정되지 않는지 검증한다."""

    @TaskHandler()
    class NoTraceHandler:
        def __init__(self) -> None:
            self.captured_ctx: TraceContext | None = None

        @task
        def simple_task(self) -> None:
            self.captured_ctx = TraceContext.get()

    handler = NoTraceHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, NoTraceHandler, handler, with_propagator=False
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]
    endpoint()

    assert handler.captured_ctx is None


def test_current_task_headers_non_dict_expect_empty() -> None:
    """current_task headers가 dict가 아니면 빈 header carrier로 처리한다."""
    post_processor = CeleryPostProcessor()
    mock_request = MagicMock()
    mock_request.get.return_value = ["not", "headers"]

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        assert post_processor._current_task_headers() == {}


def test_async_endpoint_extracts_trace_context_expect_child_span() -> None:
    """async 엔드포인트가 traceparent 헤더에서 trace context를 추출하여 child span을 생성하는지 검증한다."""

    @TaskHandler()
    class AsyncTracingHandler:
        def __init__(self) -> None:
            self.captured_ctx: TraceContext | None = None

        @task
        async def async_traced_task(self) -> None:
            self.captured_ctx = TraceContext.get()

    handler = AsyncTracingHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, AsyncTracingHandler, handler
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    mock_request = MagicMock()
    mock_request.get.return_value = {"traceparent": SAMPLE_TRACEPARENT}
    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        endpoint()

    assert handler.captured_ctx is not None
    assert handler.captured_ctx.trace_id == SAMPLE_TRACE_ID
    assert handler.captured_ctx.parent_span_id == SAMPLE_SPAN_ID
    assert handler.captured_ctx.span_id != SAMPLE_SPAN_ID
    assert TraceContext.get() is None


def test_async_endpoint_clears_trace_context_on_exception_expect_none() -> None:
    """async 엔드포인트에서 핸들러가 예외를 발생시켜도 TraceContext가 정리되는지 검증한다."""

    @TaskHandler()
    class AsyncFailingHandler:
        @task
        async def async_failing_task(self) -> None:
            raise RuntimeError("async boom")

    handler = AsyncFailingHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, AsyncFailingHandler, handler
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    mock_request = MagicMock()
    mock_request.get.return_value = {"traceparent": SAMPLE_TRACEPARENT}

    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        with pytest.raises(RuntimeError, match="async boom"):
            endpoint()

    assert TraceContext.get() is None


def test_post_processor_injects_propagator_into_dispatch_aspects_expect_set() -> None:
    """post_process()가 dispatch aspect에 propagator를 주입하는지 검증한다."""

    celery_mock = MagicMock()
    propagator = W3CTracePropagator()
    sync_aspect = CeleryTaskDispatchAspect(celery_mock)
    async_aspect = AsyncCeleryTaskDispatchAspect(celery_mock)

    application_context_mock = MagicMock()

    def get_from_context(type_: type[object]) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is ITracePropagator:
            return propagator
        if type_ is CeleryTaskDispatchAspect:
            return sync_aspect
        if type_ is AsyncCeleryTaskDispatchAspect:
            return async_aspect
        if type_ is _SampleTaskHandler:
            return _SampleTaskHandler()
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context
    application_context_mock.get_or_none.return_value = propagator
    application_context_mock.contains.return_value = True

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)
    post_processor.post_process(_SampleTaskHandler())

    assert sync_aspect._propagator is propagator
    assert async_aspect._propagator is propagator


def test_sync_endpoint_filters_non_string_headers_expect_only_strings() -> None:
    """sync 엔드포인트가 non-string 헤더 값을 필터링하는지 검증한다."""

    @TaskHandler()
    class MixedHeaderHandler:
        def __init__(self) -> None:
            self.captured_ctx: TraceContext | None = None

        @task
        def traced_task(self) -> None:
            self.captured_ctx = TraceContext.get()

    handler = MixedHeaderHandler()
    celery_mock = MagicMock()
    post_processor = _create_tracing_post_processor(
        celery_mock, MixedHeaderHandler, handler
    )
    post_processor.post_process(handler)

    endpoint = celery_mock.task.return_value.call_args_list[0].args[0]

    mock_request = MagicMock()
    # non-string 값(int, bytes 등)은 필터링되어야 함
    mock_request.get.return_value = {
        "traceparent": SAMPLE_TRACEPARENT,
        "x-numeric": 42,
        "x-bytes": b"raw",
    }
    with patch(
        "spakky.plugins.celery.post_processor.current_task"
    ) as mock_current_task:
        mock_current_task.request = mock_request
        endpoint()

    assert handler.captured_ctx is not None
    assert handler.captured_ctx.trace_id == SAMPLE_TRACE_ID
    assert TraceContext.get() is None


def test_post_processor_skips_aspect_injection_when_aspects_not_in_container() -> None:
    """dispatch aspect가 컨테이너에 없을 때 propagator 주입을 건너뛰는지 검증한다."""

    celery_mock = MagicMock()
    propagator = W3CTracePropagator()

    application_context_mock = MagicMock()

    def get_from_context(type_: type[object]) -> object:
        if type_ is Celery:
            return celery_mock
        if type_ is ITracePropagator:
            return propagator
        if type_ is _SampleTaskHandler:
            return _SampleTaskHandler()
        raise AssertionError(f"Unexpected dependency lookup: {type_}")

    application_context_mock.get.side_effect = get_from_context
    application_context_mock.get_or_none.return_value = propagator
    application_context_mock.contains.return_value = False

    post_processor = CeleryPostProcessor()
    post_processor.set_application_context(application_context_mock)

    # aspect가 컨테이너에 없어도 예외 없이 정상 처리되어야 함
    post_processor.post_process(_SampleTaskHandler())
