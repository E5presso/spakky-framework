"""Unit tests for spakky-task error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError

from spakky.task.error import (
    AbstractSpakkyTaskError,
    DuplicateTaskError,
    TaskNotFoundError,
)


def test_abstract_spakky_task_error_is_abstract() -> None:
    """AbstractSpakkyTaskError가 ABC 서브클래스인지 검증한다."""
    assert issubclass(AbstractSpakkyTaskError, ABC)


def test_abstract_spakky_task_error_inherits_from_framework_error() -> None:
    """AbstractSpakkyTaskError가 AbstractSpakkyFrameworkError를 상속하는지 검증한다."""
    assert issubclass(AbstractSpakkyTaskError, AbstractSpakkyFrameworkError)


def test_task_not_found_error_is_spakky_task_error() -> None:
    """TaskNotFoundError가 AbstractSpakkyTaskError의 서브클래스인지 검증한다."""
    assert issubclass(TaskNotFoundError, AbstractSpakkyTaskError)


def test_duplicate_task_error_is_spakky_task_error() -> None:
    """DuplicateTaskError가 AbstractSpakkyTaskError의 서브클래스인지 검증한다."""
    assert issubclass(DuplicateTaskError, AbstractSpakkyTaskError)


def test_task_not_found_error_has_message() -> None:
    """TaskNotFoundError가 message 속성을 가지는지 검증한다."""
    assert hasattr(TaskNotFoundError, "message")
    assert TaskNotFoundError.message == "Task not found in the registry"


def test_duplicate_task_error_has_message() -> None:
    """DuplicateTaskError가 message 속성을 가지는지 검증한다."""
    assert hasattr(DuplicateTaskError, "message")
    assert DuplicateTaskError.message == "Duplicate task registered"
