"""Tests for LoggingSetupPostProcessor — auto-configures logging from LoggingConfig."""

import logging

from spakky.plugins.logging.config import LogFormat, LoggingConfig
from spakky.plugins.logging.formatters import (
    SpakkyJsonFormatter,
    SpakkyPrettyFormatter,
    SpakkyTextFormatter,
)
from spakky.plugins.logging.post_processor import (
    HANDLER_NAME,
    LoggingSetupPostProcessor,
)


def _make_config(**overrides: object) -> LoggingConfig:
    """Create LoggingConfig with optional attribute overrides."""
    config = LoggingConfig()
    for key, value in overrides.items():
        # 테스트 헬퍼: 설정 오버라이드 키를 동적으로 주입
        setattr(config, key, value)
    return config


class _FakeContainer:
    """Minimal container stub that returns a LoggingConfig."""

    def __init__(self, config: LoggingConfig) -> None:
        self._config = config

    def get(self, type_: type) -> object:
        if type_ is LoggingConfig:
            return self._config
        raise AssertionError(f"Unexpected type: {type_}")


def _cleanup_spakky_handlers() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "name", None) == HANDLER_NAME:
            root.removeHandler(h)


def _make_post_processor(container: _FakeContainer) -> LoggingSetupPostProcessor:
    """Create a LoggingSetupPostProcessor with container injected via IContainerAware."""
    pp = LoggingSetupPostProcessor()
    pp.set_container(container)  # type: ignore[arg-type] - Mock 객체를 타입 인자로 전달
    return pp


def test_post_processor_configures_root_logger_expect_handler_added() -> None:
    """LoggingSetupPostProcessor가 루트 로거에 핸들러를 추가함을 검증한다."""
    _cleanup_spakky_handlers()
    config = _make_config(level=logging.DEBUG, format=LogFormat.TEXT)
    container = _FakeContainer(config)
    pp = _make_post_processor(container)

    pp.post_process(object())

    root = logging.getLogger()
    spakky_handlers = [
        h for h in root.handlers if getattr(h, "name", None) == HANDLER_NAME
    ]
    assert len(spakky_handlers) == 1
    assert isinstance(spakky_handlers[0].formatter, SpakkyTextFormatter)
    assert root.level == logging.DEBUG

    _cleanup_spakky_handlers()


def test_post_processor_json_format_expect_json_formatter() -> None:
    """LoggingSetupPostProcessor가 JSON 포맷 설정 시 SpakkyJsonFormatter를 사용함을 검증한다."""
    _cleanup_spakky_handlers()
    config = _make_config(format=LogFormat.JSON)
    container = _FakeContainer(config)
    pp = _make_post_processor(container)

    pp.post_process(object())

    root = logging.getLogger()
    spakky_handlers = [
        h for h in root.handlers if getattr(h, "name", None) == HANDLER_NAME
    ]
    assert isinstance(spakky_handlers[0].formatter, SpakkyJsonFormatter)

    _cleanup_spakky_handlers()


def test_post_processor_pretty_format_expect_pretty_formatter() -> None:
    """LoggingSetupPostProcessor가 Pretty 포맷 설정 시 SpakkyPrettyFormatter를 사용함을 검증한다."""
    _cleanup_spakky_handlers()
    config = _make_config(format=LogFormat.PRETTY)
    container = _FakeContainer(config)
    pp = _make_post_processor(container)

    pp.post_process(object())

    root = logging.getLogger()
    spakky_handlers = [
        h for h in root.handlers if getattr(h, "name", None) == HANDLER_NAME
    ]
    assert isinstance(spakky_handlers[0].formatter, SpakkyPrettyFormatter)

    _cleanup_spakky_handlers()


def test_post_processor_runs_only_once_expect_single_handler() -> None:
    """LoggingSetupPostProcessor가 여러 번 post_process해도 한 번만 구성함을 검증한다."""
    _cleanup_spakky_handlers()
    config = _make_config()
    container = _FakeContainer(config)
    pp = _make_post_processor(container)

    pp.post_process(object())
    pp.post_process(object())
    pp.post_process(object())

    root = logging.getLogger()
    spakky_handlers = [
        h for h in root.handlers if getattr(h, "name", None) == HANDLER_NAME
    ]
    assert len(spakky_handlers) == 1

    _cleanup_spakky_handlers()


def test_post_processor_package_levels_expect_per_logger_override() -> None:
    """LoggingSetupPostProcessor가 package_levels 설정에 따라 개별 로거 레벨을 설정함을 검증한다."""
    _cleanup_spakky_handlers()
    config = _make_config(
        package_levels={"spakky.test.module": logging.WARNING},
    )
    container = _FakeContainer(config)
    pp = _make_post_processor(container)

    pp.post_process(object())

    test_logger = logging.getLogger("spakky.test.module")
    assert test_logger.level == logging.WARNING

    _cleanup_spakky_handlers()


def test_post_processor_returns_pod_unchanged() -> None:
    """LoggingSetupPostProcessor가 Pod 인스턴스를 변경하지 않고 반환함을 검증한다."""
    _cleanup_spakky_handlers()
    config = _make_config()
    container = _FakeContainer(config)
    pp = _make_post_processor(container)

    sentinel = object()
    result = pp.post_process(sentinel)

    assert result is sentinel

    _cleanup_spakky_handlers()


def test_post_processor_replaces_existing_spakky_handler() -> None:
    """LoggingSetupPostProcessor가 기존 Spakky 핸들러를 교체함을 검증한다."""
    _cleanup_spakky_handlers()

    # 첫 번째 구성
    config1 = _make_config(format=LogFormat.TEXT)
    pp1 = _make_post_processor(_FakeContainer(config1))
    pp1.post_process(object())

    # 두 번째 구성 (새 PostProcessor 인스턴스)
    config2 = _make_config(format=LogFormat.JSON)
    pp2 = _make_post_processor(_FakeContainer(config2))
    pp2.post_process(object())

    root = logging.getLogger()
    spakky_handlers = [
        h for h in root.handlers if getattr(h, "name", None) == HANDLER_NAME
    ]
    assert len(spakky_handlers) == 1
    assert isinstance(spakky_handlers[0].formatter, SpakkyJsonFormatter)

    _cleanup_spakky_handlers()
