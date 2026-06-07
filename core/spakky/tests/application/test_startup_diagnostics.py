"""Tests for startup diagnostics contracts."""

import threading

import pytest
from typing import override

import spakky.core.application.application_context as application_context_module
from spakky.core.application.application import (
    STARTUP_PHASE_LOAD_PLUGINS,
    STARTUP_PHASE_REGISTRATION,
    STARTUP_PHASE_SCAN,
    SpakkyApplication,
)
from spakky.core.application.application_context import (
    STARTUP_PHASE_INSTANTIATION,
    STARTUP_PHASE_POST_PROCESSING,
    STARTUP_PHASE_POST_PROCESSOR_REGISTRATION,
    STARTUP_PHASE_SERVICE_START,
    ApplicationContext,
)
from spakky.core.application.startup_diagnostics import (
    ActiveStartupPhaseRecorder,
    IStartupDiagnosticDetailProvider,
    NoOpStartupPhaseRecorder,
    StartupDiagnosticDetail,
    StartupDiagnosticDetails,
    StartupElapsedTimeCannotBeNegativeError,
    StartupFailureSummaryNotAllowedError,
    StartupFailureSummary,
    StartupFailureSummaryRequiredError,
    StartupPhaseRecord,
    StartupPhaseStatus,
    StartupProcessedCountCannotBeNegativeError,
)
from spakky.core.pod.annotations.pod import Pod, UnexpectedDependencyTypeInjectedError
from spakky.core.pod.interfaces.post_processor import IPostProcessor
from spakky.core.service.interfaces.service import IService


class FailingStartupService(IService):
    """Synchronous service that fails during startup."""

    _stop_event: threading.Event | None
    _stopped: bool

    def __init__(self) -> None:
        self._stop_event = None
        self._stopped = False

    @override
    def set_stop_event(self, stop_event: threading.Event) -> None:
        self._stop_event = stop_event

    @override
    def start(self) -> None:
        raise RuntimeError("service failed")

    @override
    def stop(self) -> None:
        self._stopped = True


class StructuredStartupError(Exception, IStartupDiagnosticDetailProvider):
    """Startup exception exposing structured diagnostic details."""

    _details: StartupDiagnosticDetails

    def __init__(self, details: StartupDiagnosticDetails) -> None:
        self._details = details
        super().__init__("structured startup failed")

    @property
    @override
    def startup_diagnostic_details(self) -> StartupDiagnosticDetails:
        return self._details


@Pod()
class FailingPostProcessor(IPostProcessor):
    """Post-processor that fails during startup pod processing."""

    @override
    def post_process(self, pod: object) -> object:
        raise RuntimeError("post processing failed")


@Pod()
class PostProcessingTarget:
    """Pod used to trigger user post-processing during startup."""


@Pod()
class TimedInstantiationTarget:
    """Pod used to verify separate instantiation and post-processing timings."""


def test_active_startup_phase_recorder_success_expect_report_contains_phase() -> None:
    """성공한 startup phase 기록 시 report에 phase 이름과 시간이 보존됨을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()

    record = recorder.record_success(
        phase_name="scan",
        elapsed_seconds=0.25,
        processed_count=3,
    )

    assert record.phase_name == "scan"
    assert record.elapsed_seconds == 0.25
    assert record.processed_count == 3
    assert record.status == StartupPhaseStatus.SUCCESS
    assert recorder.report.records == (record,)


def test_active_startup_phase_recorder_failure_expect_structured_summary() -> None:
    """실패한 startup phase 기록 시 status와 structured error summary가 보존됨을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()
    detail = StartupDiagnosticDetail(key="phase", value="load_plugins")

    record = recorder.record_failure(
        phase_name="load_plugins",
        elapsed_seconds=0.5,
        processed_count=1,
        exception=RuntimeError("plugin load failed"),
        diagnostic_details=(detail,),
    )

    assert record.status == StartupPhaseStatus.FAILURE
    assert record.failure_summary is not None
    assert record.failure_summary.exception_type_name == "RuntimeError"
    assert record.failure_summary.message == "plugin load failed"
    assert record.failure_summary.diagnostic_details == (detail,)
    assert recorder.report.records == (record,)


def test_startup_failure_summary_from_diagnostic_exception_expect_details() -> None:
    """startup exception이 제공한 structured detail이 failure summary에 보존됨을 검증한다."""
    phase_detail = StartupDiagnosticDetail(key="phase", value="service_start")
    exception_detail = StartupDiagnosticDetail(
        key="auth.capability.validation.error",
        value="capability=AUTHENTICATION;provider_count=0",
    )

    summary = StartupFailureSummary.from_exception(
        StructuredStartupError(details=(exception_detail,)),
        diagnostic_details=(phase_detail,),
    )

    assert summary.message == "structured startup failed"
    assert summary.diagnostic_details == (phase_detail, exception_detail)


def test_active_startup_phase_recorder_zero_count_expect_preserved() -> None:
    """처리 개수 0인 startup phase가 실패 없이 그대로 기록됨을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()

    record = recorder.record_success(
        phase_name="post_processing",
        elapsed_seconds=0.0,
        processed_count=0,
    )

    assert record.processed_count == 0
    assert recorder.report.records[0].processed_count == 0


def test_no_op_startup_phase_recorder_operations_expect_no_report_side_effect() -> None:
    """No-op recorder 호출 시 report가 변경되지 않음을 검증한다."""
    recorder = NoOpStartupPhaseRecorder()

    success = recorder.record_success(
        phase_name="scan",
        elapsed_seconds=0.25,
        processed_count=2,
    )
    failure = recorder.record_failure(
        phase_name="start",
        elapsed_seconds=0.1,
        exception=RuntimeError("boom"),
    )

    assert success.status == StartupPhaseStatus.SUCCESS
    assert failure.status == StartupPhaseStatus.FAILURE
    assert recorder.report.records == ()


def test_active_startup_phase_recording_context_success_expect_measured_record() -> (
    None
):
    """record_phase context가 성공 phase를 측정하고 기록함을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()

    with recorder.record_phase(phase_name="registration") as phase:
        phase.set_processed_count(5)

    record = recorder.report.records[0]
    assert record.phase_name == "registration"
    assert record.elapsed_seconds >= 0
    assert record.processed_count == 5
    assert record.status == StartupPhaseStatus.SUCCESS


def test_active_startup_phase_recording_context_failure_expect_exception_propagated() -> (
    None
):
    """record_phase context가 실패 phase를 기록하고 기존 예외를 전파함을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()

    with pytest.raises(RuntimeError):
        with recorder.record_phase(phase_name="start", processed_count=1):
            raise RuntimeError("service failed")

    record = recorder.report.records[0]
    assert record.phase_name == "start"
    assert record.status == StartupPhaseStatus.FAILURE
    assert record.failure_summary is not None
    assert record.failure_summary.exception_type_name == "RuntimeError"
    assert record.failure_summary.message == "service failed"


def test_spakky_application_default_recorder_expect_no_op() -> None:
    """SpakkyApplication 기본 startup recorder가 no-op임을 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    app.startup_phase_recorder.record_success(
        phase_name="scan",
        elapsed_seconds=0.1,
        processed_count=1,
    )

    assert isinstance(app.startup_phase_recorder, NoOpStartupPhaseRecorder)
    assert app.startup_report.records == ()


def test_spakky_application_enable_startup_diagnostics_expect_active_report() -> None:
    """fluent API로 startup diagnostics를 활성화할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())

    result = app.enable_startup_diagnostics()
    app.startup_phase_recorder.record_success(
        phase_name="scan",
        elapsed_seconds=0.1,
        processed_count=1,
    )

    assert result is app
    assert isinstance(app.startup_phase_recorder, ActiveStartupPhaseRecorder)
    assert len(app.startup_report.records) == 1


def test_spakky_application_startup_pipeline_diagnostics_expect_phase_records() -> None:
    """diagnostics 활성화 시 startup pipeline phase들이 report에 기록됨을 검증한다."""
    from tests.dummy import dummy_package

    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins(include=set()).scan(dummy_package).start()

    try:
        records_by_phase = {
            record.phase_name: record for record in app.startup_report.records
        }

        assert records_by_phase["load_plugins"].processed_count == 0
        assert records_by_phase["scan"].processed_count > 0
        assert records_by_phase["registration"].processed_count > 0
        assert records_by_phase["post_processor_registration"].processed_count > 0
        assert records_by_phase["instantiation"].processed_count > 0
        assert records_by_phase["post_processing"].processed_count > 0
        assert records_by_phase["service_start"].processed_count == 0
        assert all(
            record.status is StartupPhaseStatus.SUCCESS
            for record in app.startup_report.records
        )
    finally:
        app.stop()


def test_spakky_application_startup_diagnostics_regression_gate_expect_report_shape() -> (
    None
):
    """startup diagnostics report가 phase 순서, count, status 의미를 구조적으로 고정한다."""
    from tests.dummy import dummy_package

    expected_phase_order = (
        STARTUP_PHASE_LOAD_PLUGINS,
        STARTUP_PHASE_SCAN,
        STARTUP_PHASE_REGISTRATION,
        STARTUP_PHASE_POST_PROCESSOR_REGISTRATION,
        STARTUP_PHASE_INSTANTIATION,
        STARTUP_PHASE_POST_PROCESSING,
        STARTUP_PHASE_SERVICE_START,
    )
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins(include=set()).scan(dummy_package).start()

    try:
        records = app.startup_report.records
        records_by_phase = {record.phase_name: record for record in records}

        assert tuple(record.phase_name for record in records) == expected_phase_order
        assert all(record.elapsed_seconds >= 0.0 for record in records)
        assert all(record.status is StartupPhaseStatus.SUCCESS for record in records)
        assert all(record.failure_summary is None for record in records)
        assert records_by_phase[STARTUP_PHASE_LOAD_PLUGINS].processed_count == 0
        assert records_by_phase[STARTUP_PHASE_SCAN].processed_count == 3
        assert records_by_phase[STARTUP_PHASE_REGISTRATION].processed_count == 4
        assert (
            records_by_phase[STARTUP_PHASE_POST_PROCESSOR_REGISTRATION].processed_count
            == 3
        )
        assert records_by_phase[STARTUP_PHASE_INSTANTIATION].processed_count == 4
        assert records_by_phase[STARTUP_PHASE_POST_PROCESSING].processed_count == 12
        assert records_by_phase[STARTUP_PHASE_SERVICE_START].processed_count == 0
    finally:
        app.stop()


def test_spakky_application_startup_diagnostics_expect_instantiation_time_excludes_post_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """instantiation phase 시간이 post_processing phase 시간과 중복되지 않음을 검증한다."""
    perf_counter_values = iter((10.0, 12.0, 13.0, 15.0, 17.0, 20.0, 23.0, 30.0))
    monkeypatch.setattr(
        application_context_module,
        "perf_counter",
        lambda: next(perf_counter_values),
    )
    app = (
        SpakkyApplication(ApplicationContext())
        .add(TimedInstantiationTarget)
        .enable_startup_diagnostics()
    )

    app.start()

    try:
        records_by_phase = {
            record.phase_name: record for record in app.startup_report.records
        }

        assert records_by_phase["post_processing"].elapsed_seconds == 12.0
        assert records_by_phase["instantiation"].elapsed_seconds == 2.0
    finally:
        app.stop()


def test_spakky_application_disabled_diagnostics_expect_existing_behavior() -> None:
    """diagnostics 비활성화 시 기존 startup behavior와 빈 report가 보존됨을 검증한다."""
    from tests.dummy import dummy_package

    app = SpakkyApplication(ApplicationContext())

    app.load_plugins(include=set()).scan(dummy_package).start()

    try:
        assert app.startup_report.records == ()
    finally:
        app.stop()


def test_spakky_application_start_without_pods_expect_zero_post_processing() -> None:
    """post-processor 적용 대상이 0개여도 post_processing phase가 실패하지 않음을 검증한다."""
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.start()

    try:
        records_by_phase = {
            record.phase_name: record for record in app.startup_report.records
        }

        assert records_by_phase["post_processing"].processed_count == 0
        assert records_by_phase["post_processing"].status is StartupPhaseStatus.SUCCESS
    finally:
        app.stop()


def test_spakky_application_start_failure_expect_recorded_and_propagated() -> None:
    """startup phase 실패 시 실패 record를 남기고 기존 예외를 그대로 전파함을 검증한다."""
    context = ApplicationContext()
    context.add_service(FailingStartupService())
    app = SpakkyApplication(context).enable_startup_diagnostics()

    try:
        with pytest.raises(RuntimeError, match="service failed"):
            app.start()

        failure = app.startup_report.records[-1]
        assert failure.phase_name == "service_start"
        assert failure.status is StartupPhaseStatus.FAILURE
        assert failure.failure_summary is not None
        assert failure.failure_summary.exception_type_name == "RuntimeError"
        assert failure.failure_summary.message == "service failed"
    finally:
        if context.is_started:
            app.stop()


def test_application_context_start_dependency_failure_summary_expect_dependency_details() -> (
    None
):
    """DI startup failure summary가 dependency diagnostic detail을 포함함을 검증한다."""

    class MissingDependency:
        """Unregistered dependency type."""

    @Pod(name="diagnostic_consumer")
    class DiagnosticConsumer:
        def __init__(self, missing: MissingDependency) -> None:
            self.missing = missing

    context = ApplicationContext()
    context.add(DiagnosticConsumer)
    recorder = ActiveStartupPhaseRecorder()

    with pytest.raises(UnexpectedDependencyTypeInjectedError):
        context.start(recorder)

    failure = recorder.report.records[-1]
    assert context.is_started is False
    assert failure.phase_name == STARTUP_PHASE_INSTANTIATION
    assert failure.status is StartupPhaseStatus.FAILURE
    assert failure.failure_summary is not None

    details = {
        detail.key: detail.value
        for detail in failure.failure_summary.diagnostic_details
    }
    assert details["failed_pod"] == "diagnostic_consumer"
    assert details["dependency_path"] == "DiagnosticConsumer.missing:MissingDependency"
    assert details["dependency_parameter"] == "missing"
    assert details["requested_type"] == "MissingDependency"


def test_spakky_application_post_processing_failure_expect_phase_failure() -> None:
    """post-processing 실패 시 해당 phase 실패 record를 남기고 기존 예외를 전파함을 검증한다."""
    context = ApplicationContext()
    app = (
        SpakkyApplication(context)
        .add(FailingPostProcessor)
        .add(PostProcessingTarget)
        .enable_startup_diagnostics()
    )

    with pytest.raises(RuntimeError, match="post processing failed"):
        app.start()

    records_by_phase = {
        record.phase_name: record for record in app.startup_report.records
    }
    instantiation = records_by_phase["instantiation"]
    post_processing = records_by_phase["post_processing"]

    assert instantiation.status is StartupPhaseStatus.SUCCESS
    assert post_processing.status is StartupPhaseStatus.FAILURE
    assert post_processing.failure_summary is not None
    assert post_processing.failure_summary.exception_type_name == "RuntimeError"
    assert post_processing.failure_summary.message == "post processing failed"


def test_startup_failure_summary_from_exception_expect_no_raw_exception() -> None:
    """failure summary가 raw exception object 없이 구조화된 필드만 보존함을 검증한다."""
    summary = StartupFailureSummary.from_exception(
        RuntimeError("startup failed"),
    )

    assert summary.exception_type_name == "RuntimeError"
    assert summary.message == "startup failed"
    assert summary.diagnostic_details == ()


def test_startup_phase_record_negative_elapsed_expect_error() -> None:
    """음수 elapsed time을 가진 phase record 생성을 차단함을 검증한다."""
    with pytest.raises(StartupElapsedTimeCannotBeNegativeError):
        StartupPhaseRecord(
            phase_name="scan",
            elapsed_seconds=-0.1,
            processed_count=0,
            status=StartupPhaseStatus.SUCCESS,
        )


def test_startup_phase_record_negative_processed_count_expect_error() -> None:
    """음수 processed count를 가진 phase record 생성을 차단함을 검증한다."""
    with pytest.raises(StartupProcessedCountCannotBeNegativeError):
        StartupPhaseRecord(
            phase_name="scan",
            elapsed_seconds=0.1,
            processed_count=-1,
            status=StartupPhaseStatus.SUCCESS,
        )


def test_startup_phase_record_success_with_failure_summary_expect_error() -> None:
    """성공 status와 failure summary가 함께 있는 phase record 생성을 차단함을 검증한다."""
    summary = StartupFailureSummary.from_exception(RuntimeError("unexpected"))

    with pytest.raises(StartupFailureSummaryNotAllowedError):
        StartupPhaseRecord(
            phase_name="scan",
            elapsed_seconds=0.1,
            processed_count=1,
            status=StartupPhaseStatus.SUCCESS,
            failure_summary=summary,
        )


def test_startup_phase_record_failure_without_failure_summary_expect_error() -> None:
    """실패 status에 failure summary가 없는 phase record 생성을 차단함을 검증한다."""
    with pytest.raises(StartupFailureSummaryRequiredError):
        StartupPhaseRecord(
            phase_name="scan",
            elapsed_seconds=0.1,
            processed_count=1,
            status=StartupPhaseStatus.FAILURE,
        )


def test_startup_phase_recording_negative_count_on_enter_expect_error() -> None:
    """record_phase 시작 시 음수 processed count를 즉시 차단함을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()

    with pytest.raises(StartupProcessedCountCannotBeNegativeError):
        recorder.record_phase(phase_name="start", processed_count=-1)


def test_startup_phase_recording_negative_count_setter_expect_error() -> None:
    """record_phase 내부에서 음수 processed count 설정을 즉시 차단함을 검증한다."""
    recorder = ActiveStartupPhaseRecorder()

    with pytest.raises(StartupProcessedCountCannotBeNegativeError):
        with recorder.record_phase(phase_name="start") as phase:
            phase.set_processed_count(-1)
