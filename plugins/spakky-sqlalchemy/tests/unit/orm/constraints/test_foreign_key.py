"""Tests for ForeignKey constraint metadata."""

from typing import Annotated, cast

from spakky.core.common.metadata import AnnotatedType

from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import (
    ForeignKey,
    ReferentialAction,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import Integer


def test_foreign_key_column_expect_value() -> None:
    """ForeignKey의 column이 올바르게 설정되는지 검증한다."""
    fk = ForeignKey(column="user.id")
    assert fk.column == "user.id"


def test_foreign_key_default_on_delete_expect_none() -> None:
    """ForeignKey의 기본 on_delete 값이 None인지 검증한다."""
    fk = ForeignKey(column="user.id")
    assert fk.on_delete is None


def test_foreign_key_default_on_update_expect_none() -> None:
    """ForeignKey의 기본 on_update 값이 None인지 검증한다."""
    fk = ForeignKey(column="user.id")
    assert fk.on_update is None


def test_foreign_key_default_name_expect_none() -> None:
    """ForeignKey의 기본 name 값이 None인지 검증한다."""
    fk = ForeignKey(column="user.id")
    assert fk.name is None


def test_foreign_key_on_delete_cascade_expect_cascade() -> None:
    """ForeignKey의 on_delete를 CASCADE로 설정할 수 있는지 검증한다."""
    fk = ForeignKey(column="user.id", on_delete=ReferentialAction.CASCADE)
    assert fk.on_delete == ReferentialAction.CASCADE


def test_foreign_key_on_delete_set_null_expect_set_null() -> None:
    """ForeignKey의 on_delete를 SET_NULL로 설정할 수 있는지 검증한다."""
    fk = ForeignKey(column="user.id", on_delete=ReferentialAction.SET_NULL)
    assert fk.on_delete == ReferentialAction.SET_NULL


def test_foreign_key_on_delete_restrict_expect_restrict() -> None:
    """ForeignKey의 on_delete를 RESTRICT로 설정할 수 있는지 검증한다."""
    fk = ForeignKey(column="user.id", on_delete=ReferentialAction.RESTRICT)
    assert fk.on_delete == ReferentialAction.RESTRICT


def test_foreign_key_on_delete_no_action_expect_no_action() -> None:
    """ForeignKey의 on_delete를 NO_ACTION으로 설정할 수 있는지 검증한다."""
    fk = ForeignKey(column="user.id", on_delete=ReferentialAction.NO_ACTION)
    assert fk.on_delete == ReferentialAction.NO_ACTION


def test_foreign_key_on_update_cascade_expect_cascade() -> None:
    """ForeignKey의 on_update를 CASCADE로 설정할 수 있는지 검증한다."""
    fk = ForeignKey(column="user.id", on_update=ReferentialAction.CASCADE)
    assert fk.on_update == ReferentialAction.CASCADE


def test_foreign_key_custom_name_expect_value() -> None:
    """ForeignKey에 커스텀 name을 설정할 수 있는지 검증한다."""
    fk = ForeignKey(column="user.id", name="fk_post_user")
    assert fk.name == "fk_post_user"


def test_foreign_key_with_all_options_expect_correct_values() -> None:
    """ForeignKey에 모든 옵션을 설정했을 때 값이 올바른지 검증한다."""
    fk = ForeignKey(
        column="category.id",
        on_delete=ReferentialAction.CASCADE,
        on_update=ReferentialAction.SET_NULL,
        name="fk_post_category",
    )
    assert fk.column == "category.id"
    assert fk.on_delete == ReferentialAction.CASCADE
    assert fk.on_update == ReferentialAction.SET_NULL
    assert fk.name == "fk_post_category"


def test_foreign_key_get_from_annotated_expect_instance() -> None:
    """Annotated 타입에서 ForeignKey 메타데이터를 추출할 수 있는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[int, Integer(), ForeignKey(column="user.id")]
    )
    fk = ForeignKey.get(annotated)
    assert isinstance(fk, ForeignKey)
    assert fk.column == "user.id"


def test_foreign_key_exists_in_annotated_expect_true() -> None:
    """Annotated 타입에 ForeignKey가 존재할 때 exists()가 True를 반환하는지 검증한다."""
    annotated = cast(
        AnnotatedType, Annotated[int, Integer(), ForeignKey(column="user.id")]
    )
    assert ForeignKey.exists(annotated) is True


def test_foreign_key_not_exists_in_annotated_expect_false() -> None:
    """Annotated 타입에 ForeignKey가 없을 때 exists()가 False를 반환하는지 검증한다."""
    annotated = cast(AnnotatedType, Annotated[int, Integer()])
    assert ForeignKey.exists(annotated) is False


def test_referential_action_cascade_value_expect_auto() -> None:
    """ReferentialAction.CASCADE의 값이 올바른지 검증한다."""
    assert ReferentialAction.CASCADE == "cascade"


def test_referential_action_set_null_value_expect_auto() -> None:
    """ReferentialAction.SET_NULL의 값이 올바른지 검증한다."""
    assert ReferentialAction.SET_NULL == "set_null"


def test_referential_action_restrict_value_expect_auto() -> None:
    """ReferentialAction.RESTRICT의 값이 올바른지 검증한다."""
    assert ReferentialAction.RESTRICT == "restrict"


def test_referential_action_no_action_value_expect_auto() -> None:
    """ReferentialAction.NO_ACTION의 값이 올바른지 검증한다."""
    assert ReferentialAction.NO_ACTION == "no_action"


def test_referential_action_is_str_enum() -> None:
    """ReferentialAction이 StrEnum인지 검증한다."""
    assert isinstance(ReferentialAction.CASCADE, str)
    assert isinstance(ReferentialAction.SET_NULL, str)
    assert isinstance(ReferentialAction.RESTRICT, str)
    assert isinstance(ReferentialAction.NO_ACTION, str)


def test_foreign_key_mutability_expect_mutable() -> None:
    """ForeignKey 인스턴스가 mutable인지 검증한다."""
    fk = ForeignKey(column="user.id")
    fk.on_delete = ReferentialAction.CASCADE
    assert fk.on_delete == ReferentialAction.CASCADE
    fk.name = "fk_updated"
    assert fk.name == "fk_updated"
