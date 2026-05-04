"""Tests for built-in actuator contributors."""

from spakky.actuator.contributors import StartupReportInfoContributor
from spakky.core.application.startup_diagnostics import (
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
