"""Unit tests for error strategy types."""

from dataclasses import FrozenInstanceError

import pytest
from spakky.saga.strategy import (
    Compensate,
    ErrorStrategy,
    ExponentialBackoff,
    Retry,
    Skip,
)


def test_compensate_instantiation_expect_success() -> None:
    """Compensate를 인스턴스화할 수 있는지 검증한다."""
    strategy = Compensate()
    assert isinstance(strategy, Compensate)


def test_skip_instantiation_expect_success() -> None:
    """Skip을 인스턴스화할 수 있는지 검증한다."""
    strategy = Skip()
    assert isinstance(strategy, Skip)


def test_exponential_backoff_default_expect_base_one() -> None:
    """ExponentialBackoff의 기본 base가 1.0인지 검증한다."""
    backoff = ExponentialBackoff()
    assert backoff.base == 1.0


def test_exponential_backoff_custom_base_expect_preserved() -> None:
    """ExponentialBackoff에 커스텀 base를 지정할 수 있는지 검증한다."""
    backoff = ExponentialBackoff(base=2.0)
    assert backoff.base == 2.0


def test_exponential_backoff_frozen_expect_frozen_instance_error() -> None:
    """ExponentialBackoff가 frozen인지 검증한다."""
    backoff = ExponentialBackoff()
    with pytest.raises(FrozenInstanceError):
        backoff.base = 2.0  # type: ignore[misc] - frozen dataclass mutation test


def test_retry_defaults_expect_correct_values() -> None:
    """Retry의 기본값을 검증한다."""
    retry = Retry()
    assert retry.max_attempts == 3
    assert retry.backoff.base == 1.0
    assert isinstance(retry.then, Compensate)


def test_retry_custom_values_expect_preserved() -> None:
    """Retry에 커스텀 값을 지정할 수 있는지 검증한다."""
    retry = Retry(
        max_attempts=5,
        backoff=ExponentialBackoff(base=2.0),
        then=Skip(),
    )
    assert retry.max_attempts == 5
    assert retry.backoff.base == 2.0
    assert isinstance(retry.then, Skip)


def test_retry_then_skip_expect_skip_instance() -> None:
    """Retry.then에 Skip을 지정할 수 있는지 검증한다."""
    retry = Retry(max_attempts=2, then=Skip())
    assert isinstance(retry.then, Skip)


def test_retry_frozen_expect_frozen_instance_error() -> None:
    """Retry가 frozen인지 검증한다."""
    retry = Retry()
    with pytest.raises(FrozenInstanceError):
        retry.max_attempts = 10  # type: ignore[misc] - frozen dataclass mutation test


def test_exponential_backoff_delay_for_expect_doubling() -> None:
    """ExponentialBackoff.delay_for가 base * 2^(attempt-1)을 반환한다."""
    backoff = ExponentialBackoff(base=0.5)
    assert backoff.delay_for(1) == 0.5
    assert backoff.delay_for(2) == 1.0
    assert backoff.delay_for(3) == 2.0
    assert backoff.delay_for(4) == 4.0


def test_error_strategy_types_expect_union_members() -> None:
    """ErrorStrategy 유니온에 Compensate, Skip, Retry가 포함되는지 검증한다."""
    compensate: ErrorStrategy = Compensate()
    skip: ErrorStrategy = Skip()
    retry: ErrorStrategy = Retry()
    assert isinstance(compensate, Compensate)
    assert isinstance(skip, Skip)
    assert isinstance(retry, Retry)
