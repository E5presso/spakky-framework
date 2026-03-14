"""Unit tests for Crontab value object."""

import pytest

from spakky.task.stereotype.crontab import Crontab, Month, Weekday


def test_crontab_default_values() -> None:
    """Crontab 기본값이 month=None, day=None, weekday=None, hour=0, minute=0인지 검증한다."""
    crontab = Crontab()
    assert crontab.month is None
    assert crontab.day is None
    assert crontab.weekday is None
    assert crontab.hour == 0
    assert crontab.minute == 0


def test_crontab_with_single_weekday() -> None:
    """단일 weekday 값이 정상 설정되는지 검증한다."""
    crontab = Crontab(hour=3, weekday=Weekday.MONDAY)
    assert crontab.hour == 3
    assert crontab.weekday == Weekday.MONDAY


def test_crontab_with_tuple_weekday() -> None:
    """tuple weekday 값이 정상 설정되는지 검증한다."""
    crontab = Crontab(
        hour=9, weekday=(Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)
    )
    assert crontab.weekday == (Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY)


def test_crontab_with_tuple_day() -> None:
    """tuple day 값이 정상 설정되는지 검증한다."""
    crontab = Crontab(day=(1, 15))
    assert crontab.day == (1, 15)


def test_crontab_with_single_month() -> None:
    """단일 month 값이 정상 설정되는지 검증한다."""
    crontab = Crontab(day=1, month=Month.JUNE)
    assert crontab.month == Month.JUNE


def test_crontab_with_tuple_month() -> None:
    """tuple month 값이 정상 설정되는지 검증한다."""
    crontab = Crontab(
        day=1, month=(Month.MARCH, Month.JUNE, Month.SEPTEMBER, Month.DECEMBER)
    )
    assert crontab.month == (Month.MARCH, Month.JUNE, Month.SEPTEMBER, Month.DECEMBER)


def test_crontab_is_frozen() -> None:
    """Crontab이 불변(frozen)인지 검증한다."""
    crontab = Crontab(hour=3)
    with pytest.raises(AttributeError):
        crontab.hour = 5  # type: ignore[misc]


def test_crontab_equality() -> None:
    """동일 값의 Crontab이 같다고 판정되는지 검증한다."""
    a = Crontab(hour=3, weekday=Weekday.MONDAY)
    b = Crontab(hour=3, weekday=Weekday.MONDAY)
    assert a == b


def test_crontab_inequality() -> None:
    """다른 값의 Crontab이 다르다고 판정되는지 검증한다."""
    a = Crontab(hour=3, weekday=Weekday.MONDAY)
    b = Crontab(hour=3, weekday=Weekday.TUESDAY)
    assert a != b
