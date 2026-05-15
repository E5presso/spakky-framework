"""Startup diagnostics report and phase recorder contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from time import perf_counter
from types import TracebackType

from typing import Self, override

from spakky.core.application.error import AbstractSpakkyApplicationError
from spakky.core.common.mutability import immutable

StartupPhaseName = str
StartupFailureMessage = str
StartupExceptionTypeName = str
StartupDiagnosticDetailKey = str
StartupDiagnosticDetailValue = str
StartupDiagnosticDetails = tuple["StartupDiagnosticDetail", ...]
StartupElapsedSeconds = float
StartupProcessedCount = int


class StartupElapsedTimeCannotBeNegativeError(AbstractSpakkyApplicationError):
    """Raised when a startup phase elapsed time is negative."""

    message = "Startup phase elapsed time cannot be negative."


class StartupProcessedCountCannotBeNegativeError(AbstractSpakkyApplicationError):
    """Raised when a startup phase processed count is negative."""

    message = "Startup phase processed count cannot be negative."


class StartupFailureSummaryRequiredError(AbstractSpakkyApplicationError):
    """Raised when a failure record has no failure summary."""

    message = "Startup failure records require a failure summary."


class StartupFailureSummaryNotAllowedError(AbstractSpakkyApplicationError):
    """Raised when a success record has a failure summary."""

    message = "Startup success records cannot include a failure summary."


class StartupPhaseStatus(StrEnum):
    """Result status for a startup phase record."""

    SUCCESS = "success"
    FAILURE = "failure"


@immutable
class StartupDiagnosticDetail:
    """Structured diagnostic detail attached to a startup failure."""

    key: StartupDiagnosticDetailKey
    """Machine-readable diagnostic detail key."""

    value: StartupDiagnosticDetailValue
    """Diagnostic detail value."""


@immutable
class StartupFailureSummary:
    """Structured startup failure summary without the raw exception object."""

    exception_type_name: StartupExceptionTypeName
    """Concrete exception type name."""

    message: StartupFailureMessage
    """Exception message captured at failure time."""

    diagnostic_details: StartupDiagnosticDetails = ()
    """Optional structured diagnostic details."""

    @classmethod
    def from_exception(
        cls,
        exception: BaseException,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> Self:
        """Create a failure summary from an exception.

        Args:
            exception: Exception raised by a startup phase.
            diagnostic_details: Optional structured diagnostic details.

        Returns:
            Failure summary containing exception type and message only.
        """
        resolved_diagnostic_details = diagnostic_details
        if isinstance(exception, IStartupDiagnosticDetailProvider):
            resolved_diagnostic_details = (
                *diagnostic_details,
                *exception.startup_diagnostic_details,
            )
        return cls(
            exception_type_name=type(exception).__name__,
            message=str(exception),
            diagnostic_details=resolved_diagnostic_details,
        )


@immutable
class StartupPhaseRecord:
    """Single startup phase timing, count, status, and failure record."""

    phase_name: StartupPhaseName
    """Name of the startup phase."""

    elapsed_seconds: StartupElapsedSeconds
    """Elapsed wall-clock seconds for the phase."""

    processed_count: StartupProcessedCount
    """Number of domain objects processed by the phase."""

    status: StartupPhaseStatus
    """Success or failure status for the phase."""

    failure_summary: StartupFailureSummary | None = None
    """Failure summary when status is failure; absent for success records."""

    diagnostic_details: StartupDiagnosticDetails = ()
    """Structured diagnostic details attached to the phase record."""

    def __post_init__(self) -> None:
        """Validate phase record numeric invariants."""
        if self.elapsed_seconds < 0:
            raise StartupElapsedTimeCannotBeNegativeError()
        if self.processed_count < 0:
            raise StartupProcessedCountCannotBeNegativeError()
        if (
            self.status is StartupPhaseStatus.SUCCESS
            and self.failure_summary is not None
        ):
            raise StartupFailureSummaryNotAllowedError()
        if self.status is StartupPhaseStatus.FAILURE and self.failure_summary is None:
            raise StartupFailureSummaryRequiredError()


class StartupReport:
    """Record collection for one application startup attempt."""

    _records: list[StartupPhaseRecord]

    def __init__(self) -> None:
        """Initialize an empty startup report."""
        self._records = []

    @property
    def records(self) -> tuple[StartupPhaseRecord, ...]:
        """Get startup phase records in insertion order.

        Returns:
            Immutable snapshot of recorded startup phases.
        """
        return tuple(self._records)

    def add_record(self, record: StartupPhaseRecord) -> None:
        """Append a phase record.

        Args:
            record: Phase record to append.
        """
        self._records.append(record)


class IStartupPhaseRecorder(ABC):
    """Interface for startup phase recorders."""

    @property
    @abstractmethod
    def report(self) -> StartupReport:
        """Get the startup report backing this recorder."""
        ...

    @abstractmethod
    def record_success(
        self,
        phase_name: StartupPhaseName,
        elapsed_seconds: StartupElapsedSeconds,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecord:
        """Record a successful startup phase."""
        ...

    @abstractmethod
    def record_failure(
        self,
        phase_name: StartupPhaseName,
        elapsed_seconds: StartupElapsedSeconds,
        exception: BaseException,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecord:
        """Record a failed startup phase."""
        ...

    def record_phase(
        self,
        phase_name: StartupPhaseName,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecording:
        """Measure a startup phase and record success or failure.

        Args:
            phase_name: Name of the startup phase.
            processed_count: Number of domain objects processed by the phase.
            diagnostic_details: Optional structured diagnostic details.

        Returns:
            Context manager that records the phase and re-raises failures.
        """
        return StartupPhaseRecording(
            recorder=self,
            phase_name=phase_name,
            processed_count=processed_count,
            diagnostic_details=diagnostic_details,
        )


class IStartupDiagnosticDetailProvider(ABC):
    """Interface for startup exceptions that expose structured diagnostics."""

    @property
    @abstractmethod
    def startup_diagnostic_details(self) -> StartupDiagnosticDetails:
        """Structured diagnostic details to attach to startup failure summaries."""
        ...


class StartupPhaseRecording:
    """Context manager for measuring and recording one startup phase."""

    _recorder: IStartupPhaseRecorder
    _phase_name: StartupPhaseName
    _processed_count: StartupProcessedCount
    _diagnostic_details: StartupDiagnosticDetails
    _started_at: float

    def __init__(
        self,
        recorder: IStartupPhaseRecorder,
        phase_name: StartupPhaseName,
        processed_count: StartupProcessedCount,
        diagnostic_details: StartupDiagnosticDetails,
    ) -> None:
        """Initialize a startup phase recording context."""
        if processed_count < 0:
            raise StartupProcessedCountCannotBeNegativeError()
        self._recorder = recorder
        self._phase_name = phase_name
        self._processed_count = processed_count
        self._diagnostic_details = diagnostic_details
        self._started_at = perf_counter()

    def __enter__(self) -> Self:
        """Enter the startup phase recording context."""
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool:
        """Record the phase outcome and preserve exception propagation."""
        elapsed_seconds = perf_counter() - self._started_at
        if exception is None:
            self._recorder.record_success(
                phase_name=self._phase_name,
                elapsed_seconds=elapsed_seconds,
                processed_count=self._processed_count,
                diagnostic_details=self._diagnostic_details,
            )
        else:
            self._recorder.record_failure(
                phase_name=self._phase_name,
                elapsed_seconds=elapsed_seconds,
                exception=exception,
                processed_count=self._processed_count,
                diagnostic_details=self._diagnostic_details,
            )
        return False

    def set_processed_count(self, processed_count: StartupProcessedCount) -> None:
        """Set the processed count before the phase exits.

        Args:
            processed_count: Final processed count for the measured phase.
        """
        if processed_count < 0:
            raise StartupProcessedCountCannotBeNegativeError()
        self._processed_count = processed_count

    def set_diagnostic_details(
        self,
        diagnostic_details: StartupDiagnosticDetails,
    ) -> None:
        """Set structured diagnostic details before the phase exits.

        Args:
            diagnostic_details: Structured diagnostic details to attach.
        """
        self._diagnostic_details = diagnostic_details


class ActiveStartupPhaseRecorder(IStartupPhaseRecorder):
    """Recorder that appends phase records to a startup report."""

    _report: StartupReport

    def __init__(self, report: StartupReport | None = None) -> None:
        """Initialize an active phase recorder.

        Args:
            report: Existing report to append to. None means create a new report.
        """
        # None means the caller did not provide an existing startup attempt report.
        self._report = report if report is not None else StartupReport()

    @property
    @override
    def report(self) -> StartupReport:
        """Get the startup report backing this recorder."""
        return self._report

    @override
    def record_success(
        self,
        phase_name: StartupPhaseName,
        elapsed_seconds: StartupElapsedSeconds,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecord:
        """Record a successful startup phase."""
        record = StartupPhaseRecord(
            phase_name=phase_name,
            elapsed_seconds=elapsed_seconds,
            processed_count=processed_count,
            status=StartupPhaseStatus.SUCCESS,
            diagnostic_details=diagnostic_details,
        )
        self._report.add_record(record)
        return record

    @override
    def record_failure(
        self,
        phase_name: StartupPhaseName,
        elapsed_seconds: StartupElapsedSeconds,
        exception: BaseException,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecord:
        """Record a failed startup phase."""
        record = StartupPhaseRecord(
            phase_name=phase_name,
            elapsed_seconds=elapsed_seconds,
            processed_count=processed_count,
            status=StartupPhaseStatus.FAILURE,
            failure_summary=StartupFailureSummary.from_exception(
                exception,
                diagnostic_details,
            ),
            diagnostic_details=diagnostic_details,
        )
        self._report.add_record(record)
        return record


class NoOpStartupPhaseRecorder(IStartupPhaseRecorder):
    """Recorder that preserves startup behavior without report side effects."""

    _report: StartupReport

    def __init__(self) -> None:
        """Initialize a no-op recorder with an empty report."""
        self._report = StartupReport()

    @property
    @override
    def report(self) -> StartupReport:
        """Get the empty report backing this recorder."""
        return self._report

    @override
    def record_success(
        self,
        phase_name: StartupPhaseName,
        elapsed_seconds: StartupElapsedSeconds,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecord:
        """Create a success record without mutating the report."""
        return StartupPhaseRecord(
            phase_name=phase_name,
            elapsed_seconds=elapsed_seconds,
            processed_count=processed_count,
            status=StartupPhaseStatus.SUCCESS,
            diagnostic_details=diagnostic_details,
        )

    @override
    def record_failure(
        self,
        phase_name: StartupPhaseName,
        elapsed_seconds: StartupElapsedSeconds,
        exception: BaseException,
        processed_count: StartupProcessedCount = 0,
        diagnostic_details: StartupDiagnosticDetails = (),
    ) -> StartupPhaseRecord:
        """Create a failure record without mutating the report."""
        return StartupPhaseRecord(
            phase_name=phase_name,
            elapsed_seconds=elapsed_seconds,
            processed_count=processed_count,
            status=StartupPhaseStatus.FAILURE,
            failure_summary=StartupFailureSummary.from_exception(
                exception,
                diagnostic_details,
            ),
            diagnostic_details=diagnostic_details,
        )
