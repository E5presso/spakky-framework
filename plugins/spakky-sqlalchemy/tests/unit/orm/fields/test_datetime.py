"""Tests for date/time field metadata types."""

from datetime import date, datetime, time, timedelta
from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.datetime import Date, DateTime, Interval, Time


def test_date_default_values_expect_abstract_field_defaults() -> None:
    """Date 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = Date()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_date_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Date 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[date, Date()])
    field = Date.get(annotated)
    assert isinstance(field, Date)


def test_date_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Date가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[date, Date()])
    assert Date.exists(annotated) is True


def test_date_with_options_expect_correct_values() -> None:
    """Date 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Date(nullable=False, name="birth_date", comment="Date of birth")
    assert field.nullable is False
    assert field.name == "birth_date"
    assert field.comment == "Date of birth"


def test_datetime_default_timezone_expect_false() -> None:
    """DateTime 필드의 기본 timezone이 False인지 검증한다."""
    field = DateTime()
    assert field.timezone is False


def test_datetime_timezone_true_expect_true() -> None:
    """DateTime 필드의 timezone을 True로 설정할 수 있는지 검증한다."""
    field = DateTime(timezone=True)
    assert field.timezone is True


def test_datetime_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 DateTime 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[datetime, DateTime(timezone=True)])
    field = DateTime.get(annotated)
    assert isinstance(field, DateTime)
    assert field.timezone is True


def test_datetime_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 DateTime이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[datetime, DateTime()])
    assert DateTime.exists(annotated) is True


def test_datetime_with_all_options_expect_correct_values() -> None:
    """DateTime 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = DateTime(
        timezone=True,
        nullable=False,
        name="created_at",
        comment="Creation timestamp",
    )
    assert field.timezone is True
    assert field.nullable is False
    assert field.name == "created_at"
    assert field.comment == "Creation timestamp"


def test_datetime_inherits_abstract_field_defaults() -> None:
    """DateTime 필드가 AbstractField의 기본값을 올바르게 상속하는지 검증한다."""
    field = DateTime()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_time_default_timezone_expect_false() -> None:
    """Time 필드의 기본 timezone이 False인지 검증한다."""
    field = Time()
    assert field.timezone is False


def test_time_timezone_true_expect_true() -> None:
    """Time 필드의 timezone을 True로 설정할 수 있는지 검증한다."""
    field = Time(timezone=True)
    assert field.timezone is True


def test_time_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Time 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[time, Time(timezone=True)])
    field = Time.get(annotated)
    assert isinstance(field, Time)
    assert field.timezone is True


def test_time_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Time이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[time, Time()])
    assert Time.exists(annotated) is True


def test_time_with_all_options_expect_correct_values() -> None:
    """Time 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Time(
        timezone=True,
        nullable=False,
        name="start_time",
        comment="Schedule start time",
    )
    assert field.timezone is True
    assert field.nullable is False
    assert field.name == "start_time"
    assert field.comment == "Schedule start time"


def test_time_inherits_abstract_field_defaults() -> None:
    """Time 필드가 AbstractField의 기본값을 올바르게 상속하는지 검증한다."""
    field = Time()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_interval_default_values_expect_abstract_field_defaults() -> None:
    """Interval 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = Interval()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_interval_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Interval 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[timedelta, Interval()])
    field = Interval.get(annotated)
    assert isinstance(field, Interval)


def test_interval_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Interval이 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[timedelta, Interval()])
    assert Interval.exists(annotated) is True


def test_interval_with_options_expect_correct_values() -> None:
    """Interval 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Interval(
        nullable=False,
        name="duration",
        comment="Task duration",
    )
    assert field.nullable is False
    assert field.name == "duration"
    assert field.comment == "Task duration"
