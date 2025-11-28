"""Test application methods for complete coverage."""

from spakky.application.application import SpakkyApplication
from spakky.application.application_context import ApplicationContext
from spakky.application.plugin import Plugin
from spakky.aspects.logging import AsyncLoggingAspect, LoggingAspect
from spakky.aspects.transactional import (
    AsyncTransactionalAspect,
    TransactionalAspect,
)


def test_add_logging_aspect() -> None:
    """Test adding LoggingAspect via add() method."""
    app = SpakkyApplication(ApplicationContext())
    app.add(LoggingAspect)
    # Check that LoggingAspect is registered
    assert any(pod.type_ == LoggingAspect for pod in app.container.pods.values())


def test_add_async_logging_aspect() -> None:
    """Test adding AsyncLoggingAspect via add() method."""
    app = SpakkyApplication(ApplicationContext())
    app.add(AsyncLoggingAspect)
    # Check that AsyncLoggingAspect is registered
    assert any(pod.type_ == AsyncLoggingAspect for pod in app.container.pods.values())


def test_add_transactional_aspect() -> None:
    """Test adding TransactionalAspect via add() method."""
    app = SpakkyApplication(ApplicationContext())
    app.add(TransactionalAspect)
    # Check that TransactionalAspect is registered
    assert any(pod.type_ == TransactionalAspect for pod in app.container.pods.values())


def test_add_async_transactional_aspect() -> None:
    """Test adding AsyncTransactionalAspect via add() method."""
    app = SpakkyApplication(ApplicationContext())
    app.add(AsyncTransactionalAspect)
    # Check that AsyncTransactionalAspect is registered
    assert any(
        pod.type_ == AsyncTransactionalAspect for pod in app.container.pods.values()
    )


def test_load_plugins_with_include() -> None:
    """Test load_plugins with include parameter."""
    app = SpakkyApplication(ApplicationContext())
    # This should not raise an error even with non-existent plugins
    app.load_plugins(include={Plugin(name="non_existent_plugin")})
    # Should complete without error
    assert app is not None


def test_stop_application() -> None:
    """Test stop method."""
    app = SpakkyApplication(ApplicationContext())
    context = app.container
    assert isinstance(context, ApplicationContext)
    app.start()
    app.stop()
    assert not context.is_started


def test_scan_with_module_path() -> None:
    """Test scan with a specific module path."""
    from tests.dummy import dummy_package

    app = SpakkyApplication(ApplicationContext())
    app.scan(dummy_package)

    # Should have scanned the module successfully
    assert len(app.container.pods) > 0
