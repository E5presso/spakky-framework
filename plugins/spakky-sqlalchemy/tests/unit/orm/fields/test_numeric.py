"""Tests for numeric field metadata types."""

from decimal import Decimal
from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    BigInteger,
    Float,
    Integer,
    Numeric,
    SmallInteger,
)


def test_integer_default_values_expect_abstract_field_defaults() -> None:
    """Integer 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = Integer()
    assert field.nullable is True
    assert field.default is None
    assert field.default_factory is None
    assert field.name == ""
    assert field.comment is None


def test_integer_get_from_annotated_expect_integer_instance() -> None:
    """Annotated 타입에서 Integer 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, Integer()])
    field = Integer.get(annotated)
    assert isinstance(field, Integer)


def test_integer_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 Integer가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, Integer()])
    assert Integer.exists(annotated) is True


def test_integer_with_options_expect_correct_values() -> None:
    """Integer 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Integer(nullable=False, default=0, name="count_col", comment="Item count")
    assert field.nullable is False
    assert field.default == 0
    assert field.name == "count_col"
    assert field.comment == "Item count"


def test_big_integer_default_values_expect_abstract_field_defaults() -> None:
    """BigInteger 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = BigInteger()
    assert field.nullable is True
    assert field.default is None


def test_big_integer_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 BigInteger 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, BigInteger()])
    field = BigInteger.get(annotated)
    assert isinstance(field, BigInteger)


def test_big_integer_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 BigInteger가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, BigInteger()])
    assert BigInteger.exists(annotated) is True


def test_big_integer_with_options_expect_correct_values() -> None:
    """BigInteger 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = BigInteger(nullable=False, name="big_id")
    assert field.nullable is False
    assert field.name == "big_id"


def test_small_integer_default_values_expect_abstract_field_defaults() -> None:
    """SmallInteger 필드가 AbstractField 기본값을 올바르게 상속하는지 검증한다."""
    field = SmallInteger()
    assert field.nullable is True
    assert field.default is None


def test_small_integer_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 SmallInteger 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, SmallInteger()])
    field = SmallInteger.get(annotated)
    assert isinstance(field, SmallInteger)


def test_small_integer_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 SmallInteger가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, SmallInteger()])
    assert SmallInteger.exists(annotated) is True


def test_small_integer_with_options_expect_correct_values() -> None:
    """SmallInteger 필드에 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = SmallInteger(nullable=False, comment="Small value")
    assert field.nullable is False
    assert field.comment == "Small value"


def test_float_default_values_expect_abstract_field_defaults() -> None:
    """Float 필드가 기본값을 올바르게 상속하는지 검증한다."""
    field = Float()
    assert field.precision is None
    assert field.decimal_return_scale is None
    assert field.nullable is True


def test_float_custom_precision_expect_value() -> None:
    """Float 필드에 precision을 설정할 수 있는지 검증한다."""
    field = Float(precision=10)
    assert field.precision == 10


def test_float_custom_decimal_return_scale_expect_value() -> None:
    """Float 필드에 decimal_return_scale을 설정할 수 있는지 검증한다."""
    field = Float(decimal_return_scale=2)
    assert field.decimal_return_scale == 2


def test_float_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Float 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[float, Float(precision=5)])
    field = Float.get(annotated)
    assert isinstance(field, Float)
    assert field.precision == 5


def test_float_with_all_options_expect_correct_values() -> None:
    """Float 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Float(
        precision=10,
        decimal_return_scale=2,
        nullable=False,
        name="price",
        comment="Product price",
    )
    assert field.precision == 10
    assert field.decimal_return_scale == 2
    assert field.nullable is False
    assert field.name == "price"
    assert field.comment == "Product price"


def test_numeric_default_values_expect_defaults() -> None:
    """Numeric 필드의 기본값들이 올바른지 검증한다."""
    field = Numeric()
    assert field.precision is None
    assert field.scale is None
    assert field.asdecimal is True
    assert field.nullable is True


def test_numeric_custom_precision_and_scale_expect_values() -> None:
    """Numeric 필드에 precision과 scale을 설정할 수 있는지 검증한다."""
    field = Numeric(precision=10, scale=2)
    assert field.precision == 10
    assert field.scale == 2


def test_numeric_asdecimal_false_expect_false() -> None:
    """Numeric 필드의 asdecimal을 False로 설정할 수 있는지 검증한다."""
    field = Numeric(asdecimal=False)
    assert field.asdecimal is False


def test_numeric_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 Numeric 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[Decimal, Numeric(precision=10, scale=2)])
    field = Numeric.get(annotated)
    assert isinstance(field, Numeric)
    assert field.precision == 10
    assert field.scale == 2


def test_numeric_with_all_options_expect_correct_values() -> None:
    """Numeric 필드에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    field = Numeric(
        precision=12,
        scale=4,
        asdecimal=True,
        nullable=False,
        name="amount",
        comment="Transaction amount",
    )
    assert field.precision == 12
    assert field.scale == 4
    assert field.asdecimal is True
    assert field.nullable is False
    assert field.name == "amount"
    assert field.comment == "Transaction amount"
