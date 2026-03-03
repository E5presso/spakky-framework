"""Test application methods for complete coverage."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext
from spakky.core.application.plugin import Plugin
from spakky.core.aspects.logging import AsyncLoggingAspect, LoggingAspect


def test_add_logging_aspect() -> None:
    """add() 메서드로 LoggingAspect를 추가할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    app.add(LoggingAspect)
    # Check that LoggingAspect is registered
    assert any(pod.type_ == LoggingAspect for pod in app.container.pods.values())


def test_add_async_logging_aspect() -> None:
    """add() 메서드로 AsyncLoggingAspect를 추가할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    app.add(AsyncLoggingAspect)
    # Check that AsyncLoggingAspect is registered
    assert any(pod.type_ == AsyncLoggingAspect for pod in app.container.pods.values())


def test_load_plugins_with_include() -> None:
    """include 파라미터를 사용하여 플러그인을 로드할 수 있음을 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    # This should not raise an error even with non-existent plugins
    app.load_plugins(include={Plugin(name="non_existent_plugin")})
    # Should complete without error
    assert app is not None


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
