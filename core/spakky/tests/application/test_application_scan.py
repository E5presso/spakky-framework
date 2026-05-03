"""Test application scan edge cases for complete coverage."""

import json
from pathlib import Path
from types import ModuleType

import pytest

from spakky.core.application.discovery_manifest import (
    DISCOVERY_MANIFEST_DETAIL_KEY,
    DEFAULT_DISCOVERY_MANIFEST_PATH,
    DiscoveryManifestCandidate,
    DiscoveryManifestDecision,
    DiscoveryManifestFingerprint,
    DiscoveryManifestStore,
)
from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.application import STARTUP_PHASE_SCAN
from spakky.core.application.startup_diagnostics import StartupPhaseRecord


def _scan_record(app: SpakkyApplication) -> StartupPhaseRecord:
    return next(
        record
        for record in app.startup_report.records
        if record.phase_name == STARTUP_PHASE_SCAN
    )


def _manifest_decision(record: StartupPhaseRecord) -> str:
    return next(
        detail.value
        for detail in record.diagnostic_details
        if detail.key == DISCOVERY_MANIFEST_DETAIL_KEY
    )


def test_scan_without_path_in_exec_context() -> None:
    """호출자 컷텍스트를 알 수 없는 경우 명시적 경로로 scan이 동작함을 검증한다."""
    # This tests the case where caller_package is None
    # which happens when __file__ is not available

    app = SpakkyApplication(ApplicationContext())

    # Create a mock situation where getattr returns None for __file__
    # This is hard to test directly, but we can at least verify
    # that scan works with explicit path
    from tests.dummy import dummy_package

    result = app.scan(dummy_package)
    assert result is app


def test_scan_with_non_package_module() -> None:
    """단일 파일 모듈(비패키지)로 scan을 수행할 수 있음을 검증한다."""
    from tests.dummy.dummy_package import module_a

    app = SpakkyApplication(ApplicationContext())
    result = app.scan(module_a)

    assert result is app
    # Should have found PodA from module_a
    assert len(app.container.pods) > 0


def test_scan_with_exclude_set() -> None:
    """exclude 파라미터를 사용하여 특정 모듈을 제외하고 scan할 수 있음을 검증한다."""
    from tests.dummy import dummy_package
    from tests.dummy.dummy_package import module_a

    app = SpakkyApplication(ApplicationContext())
    # Scan with exclusion
    result = app.scan(dummy_package, exclude={module_a})

    assert result is app


def test_scan_discovery_manifest_missing_expect_miss_recorded(
    tmp_path: Path,
) -> None:
    """manifest가 없으면 fresh discovery 후 miss decision과 manifest를 남긴다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    result = app.scan(dummy_package)

    assert result is app
    assert manifest_path.exists()
    assert _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.MISS
    assert len(app.container.pods) > 0


def test_enable_discovery_manifest_without_path_expect_project_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """manifest path 생략 시 project cache 경로를 결정적으로 사용한다."""
    monkeypatch.chdir(tmp_path)
    app = SpakkyApplication(ApplicationContext()).enable_discovery_manifest()

    assert app.discovery_manifest_path == tmp_path / DEFAULT_DISCOVERY_MANIFEST_PATH


def test_scan_discovery_manifest_unchanged_expect_hit_recorded(
    tmp_path: Path,
) -> None:
    """동일 입력 scan은 manifest hit로 기록되고 후보를 기존 등록 흐름에 재사용한다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    SpakkyApplication(ApplicationContext()).enable_discovery_manifest(
        manifest_path
    ).scan(dummy_package)
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(dummy_package)

    assert _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.HIT
    assert len(app.container.pods) > 0


def test_scan_discovery_manifest_stale_schema_expect_fresh_discovery(
    tmp_path: Path,
) -> None:
    """schema 버전이 다르면 stale_schema로 기록하고 fresh discovery를 수행한다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    manifest_path.write_text('{"schema_version": 0}', encoding="utf-8")
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(dummy_package)

    assert (
        _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.STALE_SCHEMA
    )
    assert len(app.container.pods) > 0


def test_scan_discovery_manifest_stale_exclude_expect_fresh_discovery(
    tmp_path: Path,
) -> None:
    """exclude 입력이 바뀌면 stale_input으로 기록하고 fresh discovery를 수행한다."""
    from tests.dummy import dummy_package
    from tests.dummy.dummy_package import module_a

    manifest_path = tmp_path / "discovery-manifest.json"
    SpakkyApplication(ApplicationContext()).enable_discovery_manifest(
        manifest_path
    ).scan(dummy_package)
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(dummy_package, exclude={module_a})

    assert (
        _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.STALE_INPUT
    )
    assert len(app.container.pods) > 0


def test_scan_discovery_manifest_invalid_json_expect_miss_recorded(
    tmp_path: Path,
) -> None:
    """manifest parse 실패는 miss로 기록하고 fresh discovery를 수행한다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(dummy_package)

    assert _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.MISS
    assert len(app.container.pods) > 0


def test_scan_discovery_manifest_malformed_payload_expect_miss_recorded(
    tmp_path: Path,
) -> None:
    """manifest shape이 깨진 경우 miss로 기록하고 fresh discovery를 수행한다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(dummy_package)

    assert _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.MISS
    assert len(app.container.pods) > 0


def test_scan_discovery_manifest_missing_candidate_expect_stale_input(
    tmp_path: Path,
) -> None:
    """manifest 후보가 현재 모듈에서 해소되지 않으면 stale_input으로 fresh discovery한다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    SpakkyApplication(ApplicationContext()).enable_discovery_manifest(
        manifest_path
    ).scan(dummy_package)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["candidates"][0]["qualname"] = "MissingPodA"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(dummy_package)

    assert (
        _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.STALE_INPUT
    )
    assert len(app.container.pods) > 0


def test_scan_discovery_manifest_single_module_expect_hit_recorded(
    tmp_path: Path,
) -> None:
    """단일 파일 모듈 scan도 manifest hit semantics를 유지한다."""
    from tests.dummy.dummy_package import module_a

    manifest_path = tmp_path / "discovery-manifest.json"
    SpakkyApplication(ApplicationContext()).enable_discovery_manifest(
        manifest_path
    ).scan(module_a)
    app = (
        SpakkyApplication(ApplicationContext())
        .enable_startup_diagnostics()
        .enable_discovery_manifest(manifest_path)
    )

    app.scan(module_a)

    assert _manifest_decision(_scan_record(app)) == DiscoveryManifestDecision.HIT
    assert len(app.container.pods) > 0


def test_discovery_manifest_candidate_matches_non_candidate_expect_false() -> None:
    """candidate match는 class/function 외 객체를 후보로 인정하지 않는다."""
    candidate = DiscoveryManifestCandidate(
        module_name="tests.dummy.dummy_package.module_a",
        qualname="PodA",
    )

    assert candidate.matches(object()) is False


def test_discovery_manifest_fingerprint_in_memory_module_expect_no_sources() -> None:
    """source file 없는 module scan fingerprint도 안정적으로 생성한다."""
    module = ModuleType("in_memory_module")

    fingerprint = DiscoveryManifestFingerprint.from_scan_input(
        module,
        exclude={"tests.dummy.dummy_package.module_a"},
    )

    assert fingerprint.module_name == "in_memory_module"
    assert fingerprint.sources == ()
    assert fingerprint.exclude == ("tests.dummy.dummy_package.module_a",)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": "1"},
        {"schema_version": 1, "fingerprint": [], "module_names": [], "candidates": []},
        {
            "schema_version": 1,
            "fingerprint": {
                "schema_version": "1",
                "python_version": "3.11",
                "module_name": "tests.dummy.dummy_package",
                "is_package": True,
                "exclude": [],
                "sources": [],
            },
            "module_names": [],
            "candidates": [],
        },
        {
            "schema_version": 1,
            "fingerprint": {
                "schema_version": 1,
                "python_version": 311,
                "module_name": "tests.dummy.dummy_package",
                "is_package": True,
                "exclude": [],
                "sources": [],
            },
            "module_names": [],
            "candidates": [],
        },
        {
            "schema_version": 1,
            "fingerprint": {
                "schema_version": 1,
                "python_version": "3.11",
                "module_name": 311,
                "is_package": True,
                "exclude": [],
                "sources": [],
            },
            "module_names": [],
            "candidates": [],
        },
        {
            "schema_version": 1,
            "fingerprint": {
                "schema_version": 1,
                "python_version": "3.11",
                "module_name": "tests.dummy.dummy_package",
                "is_package": "true",
                "exclude": [],
                "sources": [],
            },
            "module_names": [],
            "candidates": [],
        },
        {
            "schema_version": 1,
            "fingerprint": {
                "schema_version": 1,
                "python_version": "3.11",
                "module_name": "tests.dummy.dummy_package",
                "is_package": True,
                "exclude": "tests",
                "sources": [],
            },
            "module_names": [],
            "candidates": [],
        },
    ],
)
def test_discovery_manifest_malformed_payload_expect_store_miss(
    tmp_path: Path,
    payload: object,
) -> None:
    """manifest payload가 구조적으로 깨져 있으면 store load는 miss를 반환한다."""
    from tests.dummy import dummy_package

    manifest_path = tmp_path / "discovery-manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    fingerprint = DiscoveryManifestFingerprint.from_scan_input(dummy_package, set())

    result = DiscoveryManifestStore(manifest_path).load(fingerprint)

    assert result.decision is DiscoveryManifestDecision.MISS
