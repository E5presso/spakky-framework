"""Unit tests for error strategy types."""

from dataclasses import FrozenInstanceError

from spakky.saga.models.error_strategy import (
    Compensate,
    Retry,
    Skip,
    exponential,
)


def test_compensate_is_immutable() -> None:
    """Compensate 인스턴스가 불변인지 검증한다."""
    comp = Compensate()
    try:
        comp.x = 1  # type: ignore
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_skip_is_immutable() -> None:
    """Skip 인스턴스가 불변인지 검증한다."""
    skip = Skip()
    try:
        skip.x = 1  # type: ignore
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_retry_basic_construction() -> None:
    """Retry가 max_attempts만으로 생성 가능한지 검증한다."""
    retry = Retry(max_attempts=3)
    assert retry.max_attempts == 3
    assert retry.backoff == 1.0
    assert retry.then is Compensate


def test_retry_with_custom_backoff() -> None:
    """Retry가 커스텀 backoff 값으로 생성 가능한지 검증한다."""
    retry = Retry(max_attempts=5, backoff=2.0)
    assert retry.max_attempts == 5
    assert retry.backoff == 2.0


def test_retry_with_skip_then_strategy() -> None:
    """Retry에 then=Skip 전략을 설정할 수 있는지 검증한다."""
    retry = Retry(max_attempts=2, then=Skip)
    assert retry.then is Skip


def test_retry_is_immutable() -> None:
    """Retry 인스턴스가 불변인지 검증한다."""
    retry = Retry(max_attempts=3)
    try:
        retry.max_attempts = 5  # type: ignore
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_exponential_default_base() -> None:
    """exponential이 기본 base=1.0을 반환하는지 검증한다."""
    assert exponential() == 1.0


def test_exponential_custom_base() -> None:
    """exponential이 커스텀 base 값을 반환하는지 검증한다."""
    assert exponential(base=2.0) == 2.0


def test_retry_with_exponential_backoff() -> None:
    """Retry가 exponential backoff와 함께 동작하는지 검증한다."""
    retry = Retry(max_attempts=3, backoff=exponential(base=1.5))
    assert retry.backoff == 1.5
