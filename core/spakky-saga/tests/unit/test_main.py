"""Unit tests for spakky-saga plugin initialization."""

from spakky.core.application.application import SpakkyApplication
from spakky.core.application.application_context import ApplicationContext

from spakky.saga.main import initialize


def test_initialize_does_not_raise_expect_noop() -> None:
    """spakky-saga initialize가 SpakkyApplication을 받아 정상 완료되는지 검증한다."""
    app = SpakkyApplication(ApplicationContext())
    initialize(app)
