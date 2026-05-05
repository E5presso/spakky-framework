"""Conformance tests for feature contribution loading."""

from collections.abc import Callable
from dataclasses import dataclass

import pytest

import spakky.core.application.application as application_module
from spakky.core.application.application import (
    STARTUP_PHASE_LOAD_PLUGINS,
    SpakkyApplication,
)
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.application.startup_diagnostics import StartupPhaseStatus


@dataclass(frozen=True)
class FakeDistributionEntryPoint:
    name: str
    group: str


@dataclass(frozen=True)
class FakeDistribution:
    entry_points: tuple[FakeDistributionEntryPoint, ...]


@dataclass(frozen=True)
class FakeEntryPoint:
    name: str
    value: str
    initializer: Callable[[SpakkyApplication], None]
    dist: FakeDistribution | None = None

    def load(self) -> Callable[[SpakkyApplication], None]:
        return self.initializer


def _recording_initializer(
    calls: list[str],
    label: str,
) -> Callable[[SpakkyApplication], None]:
    def initialize(_app: SpakkyApplication) -> None:
        calls.append(label)

    return initialize


def _failing_initializer(_app: SpakkyApplication) -> None:
    raise RuntimeError("contribution failed")


def _provider_distribution(provider_name: str) -> FakeDistribution:
    return FakeDistribution(
        entry_points=(
            FakeDistributionEntryPoint(
                name=provider_name,
                group="spakky.plugins",
            ),
        )
    )


def _load_plugins_diagnostic_values(
    app: SpakkyApplication,
) -> dict[str, tuple[str, ...]]:
    records_by_phase = {
        record.phase_name: record for record in app.startup_report.records
    }
    details_by_key: dict[str, list[str]] = {}
    for detail in records_by_phase[STARTUP_PHASE_LOAD_PLUGINS].diagnostic_details:
        details_by_key.setdefault(detail.key, []).append(detail.value)
    return {key: tuple(values) for key, values in details_by_key.items()}


def test_contribution_loader_conformance_expect_ordered_state_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """loaded/skipped/failed contribution state를 deterministic fake EP로 고정한다."""
    calls: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-a-feature",
                    value="spakky.a_feature.main:initialize",
                    initializer=_recording_initializer(calls, "base:a-feature"),
                ),
                FakeEntryPoint(
                    name="spakky-outbox",
                    value="spakky.outbox.main:initialize",
                    initializer=_recording_initializer(calls, "base:outbox"),
                ),
                FakeEntryPoint(
                    name="spakky-sqlalchemy",
                    value="spakky.plugins.sqlalchemy.main:initialize",
                    initializer=_recording_initializer(calls, "base:sqlalchemy"),
                ),
            )
        if group == "spakky.contributions.spakky.a.feature":
            return (
                FakeEntryPoint(
                    name="a-loaded",
                    value="example.loaded:initialize",
                    initializer=_recording_initializer(calls, "contribution:loaded"),
                    dist=_provider_distribution("spakky-sqlalchemy"),
                ),
                FakeEntryPoint(
                    name="z-inactive-provider",
                    value="example.inactive_provider:initialize",
                    initializer=_recording_initializer(
                        calls,
                        "contribution:inactive-provider",
                    ),
                    dist=_provider_distribution("spakky-rabbitmq"),
                ),
            )
        if group == "spakky.contributions.spakky.outbox":
            return (
                FakeEntryPoint(
                    name="failed",
                    value="example.failed:initialize",
                    initializer=_failing_initializer,
                    dist=_provider_distribution("spakky-sqlalchemy"),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    with pytest.raises(RuntimeError, match="contribution failed"):
        app.load_plugins()

    record = app.startup_report.records[0]
    details = _load_plugins_diagnostic_values(app)
    assert record.status is StartupPhaseStatus.FAILURE
    assert calls == [
        "base:a-feature",
        "base:outbox",
        "base:sqlalchemy",
        "contribution:loaded",
    ]
    assert details["contributions.loaded"] == ("1",)
    assert details["contributions.skipped"] == ("1",)
    assert details["contributions.failed"] == ("1",)
    assert details["contributions.skipped.inactive_provider"] == ("1",)


@pytest.mark.parametrize(
    ("include", "expected_calls", "expected_loaded", "expected_skip_key"),
    [
        (
            None,
            ("base:outbox", "base:sqlalchemy", "contribution:sqlalchemy-outbox"),
            "1",
            None,
        ),
        (
            {Plugin(name="spakky-outbox"), Plugin(name="spakky-sqlalchemy")},
            ("base:outbox", "base:sqlalchemy", "contribution:sqlalchemy-outbox"),
            "1",
            None,
        ),
        (
            {Plugin(name="spakky-outbox")},
            ("base:outbox",),
            "0",
            "contributions.skipped.include_filter",
        ),
        (
            {Plugin(name="spakky-sqlalchemy")},
            ("base:sqlalchemy",),
            "0",
            "contributions.skipped.inactive_feature",
        ),
        (
            set(),
            (),
            "0",
            "contributions.skipped.inactive_feature",
        ),
    ],
)
def test_contribution_loader_conformance_include_matrix(
    monkeypatch: pytest.MonkeyPatch,
    include: set[Plugin] | None,
    expected_calls: tuple[str, ...],
    expected_loaded: str,
    expected_skip_key: str | None,
) -> None:
    """include matrix는 feature와 provider 둘 다 active일 때만 contribution을 로드한다."""
    calls: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-outbox",
                    value="spakky.outbox.main:initialize",
                    initializer=_recording_initializer(calls, "base:outbox"),
                ),
                FakeEntryPoint(
                    name="spakky-sqlalchemy",
                    value="spakky.plugins.sqlalchemy.main:initialize",
                    initializer=_recording_initializer(calls, "base:sqlalchemy"),
                ),
            )
        if group == "spakky.contributions.spakky.outbox":
            return (
                FakeEntryPoint(
                    name="sqlalchemy-outbox",
                    value="spakky.plugins.sqlalchemy.contributions.outbox:initialize",
                    initializer=_recording_initializer(
                        calls,
                        "contribution:sqlalchemy-outbox",
                    ),
                    dist=_provider_distribution("spakky-sqlalchemy"),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins(include=include)

    details = _load_plugins_diagnostic_values(app)
    assert tuple(calls) == expected_calls
    assert details["contributions.loaded"] == (expected_loaded,)
    if expected_skip_key is None:
        assert details["contributions.skipped"] == ("0",)
    else:
        assert details["contributions.skipped"] == ("1",)
        assert details[expected_skip_key] == ("1",)
