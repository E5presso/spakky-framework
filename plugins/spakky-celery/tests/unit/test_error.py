"""Tests for Celery error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError

from spakky.plugins.celery.error import AbstractSpakkyCeleryError


def test_abstract_spakky_celery_error_is_abstract() -> None:
    """AbstractSpakkyCeleryError가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSpakkyCeleryError, ABC)


def test_abstract_spakky_celery_error_inherits_from_framework_error() -> None:
    """AbstractSpakkyCeleryError가 AbstractSpakkyFrameworkError를 상속하는지 검증한다."""
    assert issubclass(AbstractSpakkyCeleryError, AbstractSpakkyFrameworkError)
