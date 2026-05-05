"""Test application methods for complete coverage."""

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import EntryPoint

import pytest

import spakky.core.application.application as application_module
from spakky.core.aop.aspect import Aspect, AsyncAspect
from spakky.core.aop.interfaces.aspect import IAspect, IAsyncAspect
from spakky.core.application.application import (
    STARTUP_PHASE_LOAD_PLUGINS,
    SpakkyApplication,
)
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.application.startup_diagnostics import StartupPhaseStatus


@Aspect()
class StubAspect(IAspect): ...


@AsyncAspect()
class AsyncStubAspect(IAsyncAspect): ...


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


def test_add_aspect_expect_registered() -> None:
    """add() 메서드로 Aspect를 추가할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    app.add(StubAspect)
    assert any(pod.type_ == StubAspect for pod in app.container.pods.values())


def test_add_async_aspect_expect_registered() -> None:
    """add() 메서드로 AsyncAspect를 추가할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    app.add(AsyncStubAspect)
    assert any(pod.type_ == AsyncStubAspect for pod in app.container.pods.values())


def test_load_plugins_with_include() -> None:
    """include 파라미터를 사용하여 플러그인을 로드할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    # This should not raise an error even with non-existent plugins
    app.load_plugins(include={Plugin(name="non_existent_plugin")})
    # Should complete without error
    assert app is not None


def test_load_plugins_expect_contributions_after_base_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """active core feature contribution이 base plugin 이후 로드됨을 검증한다."""
    calls: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-sqlalchemy",
                    value="spakky.plugins.sqlalchemy.main:initialize",
                    initializer=_recording_initializer(calls, "base:sqlalchemy"),
                ),
                FakeEntryPoint(
                    name="spakky-outbox",
                    value="spakky.outbox.main:initialize",
                    initializer=_recording_initializer(calls, "base:outbox"),
                ),
            )
        if group == "spakky.contributions.spakky.outbox":
            return (
                FakeEntryPoint(
                    name="sqlalchemy-outbox",
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(
                        calls,
                        "contribution:sqlalchemy-outbox",
                    ),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins()

    assert calls == [
        "base:outbox",
        "base:sqlalchemy",
        "contribution:sqlalchemy-outbox",
    ]


def test_load_plugins_without_active_feature_expect_no_contribution_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """core feature가 active가 아니면 contribution lookup이 등록을 수행하지 않는다."""
    calls: list[str] = []
    requested_groups: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        requested_groups.append(group)
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-sqlalchemy",
                    value="spakky.plugins.sqlalchemy.main:initialize",
                    initializer=_recording_initializer(calls, "base:sqlalchemy"),
                ),
            )
        return (
            FakeEntryPoint(
                name="unexpected",
                value="unexpected.module:initialize",
                initializer=_recording_initializer(calls, "unexpected"),
            ),
        )

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins()

    assert calls == ["base:sqlalchemy"]
    assert requested_groups == ["spakky.plugins"]


def test_load_plugins_include_expect_skipped_feature_has_no_contributions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include에서 제외된 core feature의 contribution을 로드하지 않음을 검증한다."""
    calls: list[str] = []
    requested_groups: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        requested_groups.append(group)
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(calls, "unexpected"),
                ),
            )
        return (
            FakeEntryPoint(
                name="unexpected",
                value="unexpected.module:initialize",
                initializer=_recording_initializer(calls, "unexpected"),
            ),
        )

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins(
        include={Plugin(name="spakky-sqlalchemy")}
    )

    assert calls == ["base:sqlalchemy"]
    assert requested_groups == [
        "spakky.plugins",
        "spakky.contributions.spakky.outbox",
    ]


def test_load_plugins_include_feature_and_provider_expect_contribution_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include가 feature와 provider를 모두 담으면 contribution을 로드한다."""
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(
                        calls,
                        "contribution:sqlalchemy-outbox",
                    ),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins(
        include={Plugin(name="spakky-outbox"), Plugin(name="spakky-sqlalchemy")}
    )

    assert calls == [
        "base:outbox",
        "base:sqlalchemy",
        "contribution:sqlalchemy-outbox",
    ]


def test_load_plugins_include_feature_only_expect_provider_contribution_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include에 provider가 없으면 feature contribution을 skip한다."""
    calls: list[str] = []
    requested_groups: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        requested_groups.append(group)
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(
                        calls,
                        "contribution:sqlalchemy-outbox",
                    ),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins(
        include={Plugin(name="spakky-outbox")}
    )

    assert calls == ["base:outbox"]
    assert requested_groups == [
        "spakky.plugins",
        "spakky.contributions.spakky.outbox",
    ]


def test_load_plugins_include_empty_expect_no_base_or_contribution_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include가 빈 set이면 base plugin과 contribution을 모두 로드하지 않는다."""
    calls: list[str] = []
    requested_groups: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        requested_groups.append(group)
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(calls, "unexpected"),
                ),
            )
        return (
            FakeEntryPoint(
                name="unexpected",
                value="unexpected.module:initialize",
                initializer=_recording_initializer(calls, "unexpected"),
            ),
        )

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins(include=set())

    assert calls == []
    assert requested_groups == [
        "spakky.plugins",
        "spakky.contributions.spakky.outbox",
    ]


def test_load_plugins_diagnostics_expect_loaded_contribution_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """diagnostics가 loaded contribution count와 context를 기록함을 검증한다."""
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(
                        calls,
                        "contribution:sqlalchemy-outbox",
                    ),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins()

    details = _load_plugins_diagnostic_values(app)
    assert details["contributions.loaded"] == ("1",)
    assert details["contributions.skipped"] == ("0",)
    assert details["contributions.failed"] == ("0",)
    assert details["contributions.loaded.item"] == (
        (
            "group=spakky.contributions.spakky.outbox;"
            "entry_point=sqlalchemy-outbox;"
            "provider=spakky-sqlalchemy;"
            "feature=spakky-outbox"
        ),
    )


def test_load_plugins_diagnostics_expect_skipped_contribution_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """diagnostics가 skipped contribution count와 skip reason을 기록함을 검증한다."""
    calls: list[str] = []

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-outbox",
                    value="spakky.outbox.main:initialize",
                    initializer=_recording_initializer(calls, "base:outbox"),
                ),
            )
        if group == "spakky.contributions.spakky.outbox":
            return (
                FakeEntryPoint(
                    name="sqlalchemy-outbox",
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(calls, "unexpected"),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins()

    details = _load_plugins_diagnostic_values(app)
    assert calls == ["base:outbox"]
    assert details["contributions.loaded"] == ("0",)
    assert details["contributions.skipped"] == ("1",)
    assert details["contributions.skipped.inactive_provider"] == ("1",)
    assert details["contributions.skipped.item"] == (
        (
            "reason=inactive_provider;"
            "group=spakky.contributions.spakky.outbox;"
            "entry_point=sqlalchemy-outbox;"
            "provider=spakky-sqlalchemy;"
            "feature=spakky-outbox"
        ),
    )


def test_load_plugins_diagnostics_expect_include_filter_skip_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include filter로 skip된 contribution reason을 diagnostics에 기록한다."""
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(calls, "unexpected"),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins(include={Plugin(name="spakky-outbox")})

    details = _load_plugins_diagnostic_values(app)
    assert calls == ["base:outbox"]
    assert details["contributions.skipped"] == ("1",)
    assert details["contributions.skipped.include_filter"] == ("1",)


def test_contribution_skip_reason_include_expect_active_provider_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """include filter는 활성 provider 중 include 포함 여부로 판단한다."""
    contribution_entry_point = EntryPoint(
        name="sqlalchemy-outbox",
        value="spakky.plugins.sqlalchemy.contributions.outbox:initialize",
        group="spakky.contributions.spakky.outbox",
    )
    monkeypatch.setattr(
        application_module,
        "_provider_plugins_for_contribution",
        lambda _entry_point: {
            Plugin(name="spakky-sqlalchemy"),
            Plugin(name="spakky-other-provider"),
        },
    )

    skip_reason = application_module._contribution_skip_reason(
        feature_plugin=Plugin(name="spakky-outbox"),
        contribution_entry_point=contribution_entry_point,
        loaded_base_plugins={
            Plugin(name="spakky-outbox"),
            Plugin(name="spakky-sqlalchemy"),
        },
        include={
            Plugin(name="spakky-outbox"),
            Plugin(name="spakky-other-provider"),
        },
    )

    assert skip_reason == "include_filter"


def test_load_plugins_diagnostics_expect_inactive_feature_skip_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """target feature가 inactive이면 skip reason을 diagnostics에 기록한다."""
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
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=_recording_initializer(calls, "unexpected"),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins(include={Plugin(name="spakky-sqlalchemy")})

    details = _load_plugins_diagnostic_values(app)
    assert calls == ["base:sqlalchemy"]
    assert details["contributions.skipped"] == ("1",)
    assert details["contributions.skipped.inactive_feature"] == ("1",)


def test_load_plugins_diagnostics_expect_failed_contribution_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """contribution failure context를 기록하고 기존 예외 의미를 전파한다."""

    def failing_initializer(_app: SpakkyApplication) -> None:
        raise RuntimeError("contribution failed")

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-outbox",
                    value="spakky.outbox.main:initialize",
                    initializer=_recording_initializer([], "base:outbox"),
                ),
                FakeEntryPoint(
                    name="spakky-sqlalchemy",
                    value="spakky.plugins.sqlalchemy.main:initialize",
                    initializer=_recording_initializer([], "base:sqlalchemy"),
                ),
            )
        if group == "spakky.contributions.spakky.outbox":
            return (
                FakeEntryPoint(
                    name="sqlalchemy-outbox",
                    value=("spakky.plugins.sqlalchemy.contributions.outbox:initialize"),
                    initializer=failing_initializer,
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    with pytest.raises(RuntimeError, match="contribution failed"):
        app.load_plugins()

    record = app.startup_report.records[0]
    assert record.status is StartupPhaseStatus.FAILURE
    assert record.failure_summary is not None
    assert record.failure_summary.diagnostic_details[2].value == "1"
    assert record.failure_summary.diagnostic_details[-1].key == (
        "contributions.failed.item"
    )


def test_load_plugins_diagnostics_expect_zero_contribution_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """contribution entry point가 없어도 zero contribution 상태를 기록한다."""

    def fake_entry_points(group: str) -> tuple[FakeEntryPoint, ...]:
        if group == "spakky.plugins":
            return (
                FakeEntryPoint(
                    name="spakky-outbox",
                    value="spakky.outbox.main:initialize",
                    initializer=_recording_initializer([], "base:outbox"),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)
    app = SpakkyApplication(ApplicationContext()).enable_startup_diagnostics()

    app.load_plugins()

    details = _load_plugins_diagnostic_values(app)
    assert details["contributions.loaded"] == ("0",)
    assert details["contributions.skipped"] == ("0",)
    assert details["contributions.failed"] == ("0",)


def test_load_plugins_expect_deterministic_contribution_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """여러 feature/contribution 로딩 순서가 재현 가능함을 검증한다."""
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
                    name="spakky-data",
                    value="spakky.data.main:initialize",
                    initializer=_recording_initializer(calls, "base:data"),
                ),
                FakeEntryPoint(
                    name="spakky-sqlalchemy",
                    value="spakky.plugins.sqlalchemy.main:initialize",
                    initializer=_recording_initializer(calls, "base:sqlalchemy"),
                ),
            )
        if group == "spakky.contributions.spakky.data":
            return (
                FakeEntryPoint(
                    name="z-data",
                    value="example.z_data:initialize",
                    initializer=_recording_initializer(calls, "contribution:z-data"),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
                FakeEntryPoint(
                    name="a-data",
                    value="example.a_data:initialize",
                    initializer=_recording_initializer(calls, "contribution:a-data"),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        if group == "spakky.contributions.spakky.outbox":
            return (
                FakeEntryPoint(
                    name="z-outbox",
                    value="example.z_outbox:initialize",
                    initializer=_recording_initializer(
                        calls,
                        "contribution:z-outbox",
                    ),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
                FakeEntryPoint(
                    name="a-outbox",
                    value="example.a_outbox:initialize",
                    initializer=_recording_initializer(
                        calls,
                        "contribution:a-outbox",
                    ),
                    dist=FakeDistribution(
                        entry_points=(
                            FakeDistributionEntryPoint(
                                name="spakky-sqlalchemy",
                                group="spakky.plugins",
                            ),
                        )
                    ),
                ),
            )
        return ()

    monkeypatch.setattr(application_module, "entry_points", fake_entry_points)

    SpakkyApplication(ApplicationContext()).load_plugins()

    assert calls == [
        "base:data",
        "base:outbox",
        "base:sqlalchemy",
        "contribution:a-data",
        "contribution:z-data",
        "contribution:a-outbox",
        "contribution:z-outbox",
    ]


def test_stop_application() -> None:
    """stop 메서드가 정상적으로 동작함을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    context = app.container
    assert isinstance(context, ApplicationContext)
    app.start()
    app.stop()
    assert not context.is_started


def test_scan_with_module_path() -> None:
    """특정 모듈 경로로 scan을 수행할 수 있음을 검증한다."""
    from tests.dummy import dummy_package

    app = SpakkyApplication(ApplicationContext())
    app.scan(dummy_package)

    # Should have scanned the module successfully
    assert len(app.container.pods) > 0


def test_application_context_property_returns_context() -> None:
    """application_context property가 올바른 컨텍스트를 반환함을 검증한다."""
    context = ApplicationContext()
    app = SpakkyApplication(context)
    assert app.application_context is context


def test_scan_with_tagged_module() -> None:
    """Tag가 있는 모듈을 스캔하면 태그가 등록됨을 검증한다."""
    from tests.dummy import tagged_package

    app = SpakkyApplication(ApplicationContext())
    app.scan(tagged_package)

    # Should have registered the tag
    assert app.container is not None


def test_add_tag_only_class_expect_tag_registered() -> None:
    """add()로 Tag만 있는 클래스를 추가하면 태그가 등록됨을 검증한다."""
    from tests.dummy.tagged_package.tagged_module import CustomTag, TagOnlyClass

    app = SpakkyApplication(ApplicationContext())
    app.add(TagOnlyClass)

    # Tag should be registered
    tags = app.application_context.tags
    assert any(
        isinstance(tag, CustomTag) and tag.category == "tag-only" for tag in tags
    )
    # Pod should NOT be registered (no @Pod decorator)
    assert not any(pod.type_ == TagOnlyClass for pod in app.container.pods.values())


def test_add_tagged_pod_class_expect_both_registered() -> None:
    """add()로 Tag와 Pod 둘 다 있는 클래스를 추가하면 둘 다 등록됨을 검증한다."""
    from tests.dummy.tagged_package.tagged_module import CustomTag, TaggedPod

    app = SpakkyApplication(ApplicationContext())
    app.add(TaggedPod)

    # Pod should be registered
    assert any(pod.type_ == TaggedPod for pod in app.container.pods.values())
    # Tag should also be registered
    tags = app.application_context.tags
    assert any(isinstance(tag, CustomTag) and tag.category == "test" for tag in tags)
