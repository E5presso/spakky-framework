"""Built-in actuator info contributors."""

from collections.abc import Callable, Mapping

from spakky.core.application.startup_diagnostics import (
    StartupPhaseRecord,
    StartupReport,
)

from spakky.actuator.interfaces.contributor import IInfoContributor


class StartupReportInfoContributor(IInfoContributor):
    """Expose startup diagnostics through actuator info."""

    def __init__(self, report_provider: Callable[[], StartupReport]) -> None:
        self._report_provider = report_provider

    @property
    def name(self) -> str:
        return "startup"

    def contribute_info(self) -> Mapping[str, object]:
        records = self._report_provider().records
        return {
            "startup": {
                "phase_count": len(records),
                "records": tuple(_record_payload(record) for record in records),
                "total_elapsed_seconds": _total_elapsed_seconds(records),
            }
        }


def _total_elapsed_seconds(records: tuple[StartupPhaseRecord, ...]) -> float:
    return sum(record.elapsed_seconds for record in records)


def _record_payload(record: StartupPhaseRecord) -> Mapping[str, object]:
    payload: dict[str, object] = {
        "diagnostic_details": tuple(
            {"key": detail.key, "value": detail.value}
            for detail in record.diagnostic_details
        ),
        "elapsed_seconds": record.elapsed_seconds,
        "phase_name": record.phase_name,
        "processed_count": record.processed_count,
        "status": record.status.value,
    }
    if record.failure_summary is not None:
        payload["failure"] = {
            "diagnostic_details": tuple(
                {"key": detail.key, "value": detail.value}
                for detail in record.failure_summary.diagnostic_details
            ),
            "exception_type_name": record.failure_summary.exception_type_name,
            "message": record.failure_summary.message,
        }
    return payload
