"""Tests for built-in actuator contributors."""

from spakky.actuator.contributors import StartupReportInfoContributor
from spakky.core.application.startup_diagnostics import (
    StartupDiagnosticDetail,
    StartupFailureSummary,
    StartupPhaseStatus,
    StartupReport,
    StartupPhaseRecord,
)


def test_startup_report_contributor_expect_deterministic_info_payload() -> None:
    """startup report contributor가 phase records를 info payload로 노출하는지 검증한다."""
    report = StartupReport()
    report.add_record(
        StartupPhaseRecord(
            phase_name="scan",
            elapsed_seconds=0.25,
            processed_count=3,
            status=StartupPhaseStatus.SUCCESS,
        )
    )
    contributor = StartupReportInfoContributor(lambda: report)

    payload = contributor.contribute_info()

    assert contributor.name == "startup"
    assert payload == {
        "startup": {
            "phase_count": 1,
            "records": (
                {
                    "diagnostic_details": (),
                    "elapsed_seconds": 0.25,
                    "phase_name": "scan",
                    "processed_count": 3,
                    "status": "success",
                },
            ),
            "total_elapsed_seconds": 0.25,
        }
    }


def test_startup_report_contributor_expect_failure_payload_includes_summary() -> None:
    """startup failure record가 actuator info에 구조화된 failure로 노출되는지 검증한다."""
    report = StartupReport()
    report.add_record(
        StartupPhaseRecord(
            phase_name="instantiate",
            elapsed_seconds=0.5,
            processed_count=2,
            status=StartupPhaseStatus.FAILURE,
            failure_summary=StartupFailureSummary(
                exception_type_name="RuntimeError",
                message="boom",
                diagnostic_details=(
                    StartupDiagnosticDetail(key="pod", value="BrokenService"),
                ),
            ),
            diagnostic_details=(StartupDiagnosticDetail(key="phase", value="pod"),),
        )
    )
    contributor = StartupReportInfoContributor(lambda: report)

    payload = contributor.contribute_info()

    assert payload == {
        "startup": {
            "phase_count": 1,
            "records": (
                {
                    "diagnostic_details": ({"key": "phase", "value": "pod"},),
                    "elapsed_seconds": 0.5,
                    "failure": {
                        "diagnostic_details": (
                            {"key": "pod", "value": "BrokenService"},
                        ),
                        "exception_type_name": "RuntimeError",
                        "message": "boom",
                    },
                    "phase_name": "instantiate",
                    "processed_count": 2,
                    "status": "failure",
                },
            ),
            "total_elapsed_seconds": 0.5,
        }
    }
