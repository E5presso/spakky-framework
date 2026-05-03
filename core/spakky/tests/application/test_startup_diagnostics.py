"""Tests for startup diagnostics contracts."""

import pytest

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.startup_diagnostics import (
    ActiveStartupPhaseRecorder,
    NoOpStartupPhaseRecorder,
    StartupDiagnosticDetail,
    StartupElapsedTimeCannotBeNegativeError,
    StartupFailureSummary,
    StartupPhaseRecord,
    StartupPhaseStatus,
    StartupProcessedCountCannotBeNegativeError,
)


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
