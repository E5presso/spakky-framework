"""Unit tests for CascadeOption Flag enum."""

from spakky.plugins.sqlalchemy.orm.relationships.cascade import CascadeOption


def test_cascade_option_none_to_string_expect_none_string() -> None:
    """CascadeOption.NONE을 문자열로 변환하면 'none'이 반환되어야 한다."""
    result = CascadeOption.NONE.to_string()

    assert result == "none"


def test_cascade_option_single_flag_to_string_expect_correct_format() -> None:
    """단일 CascadeOption 플래그를 문자열로 변환하면 올바른 형식이 반환되어야 한다."""
    assert CascadeOption.SAVE_UPDATE.to_string() == "save-update"
    assert CascadeOption.MERGE.to_string() == "merge"
    assert CascadeOption.EXPUNGE.to_string() == "expunge"
    assert CascadeOption.DELETE.to_string() == "delete"
    assert CascadeOption.DELETE_ORPHAN.to_string() == "delete-orphan"
    assert CascadeOption.REFRESH_EXPIRE.to_string() == "refresh-expire"


def test_cascade_option_combined_flags_to_string_expect_comma_separated() -> None:
    """여러 CascadeOption 플래그를 결합하면 쉼표로 구분된 문자열이 반환되어야 한다."""
    combined = CascadeOption.SAVE_UPDATE | CascadeOption.MERGE

    result = combined.to_string()

    assert "save-update" in result
    assert "merge" in result


def test_cascade_option_all_to_string_expect_all() -> None:
    """CascadeOption.ALL을 문자열로 변환하면 'all'이 반환되어야 한다."""
    result = CascadeOption.ALL.to_string()

    assert result == "all"


def test_cascade_option_all_delete_orphan_to_string_expect_all_delete_orphan() -> None:
    """CascadeOption.ALL_DELETE_ORPHAN을 문자열로 변환하면 'all, delete-orphan'이 반환되어야 한다."""
    result = CascadeOption.ALL_DELETE_ORPHAN.to_string()

    assert result == "all, delete-orphan"


def test_cascade_option_all_or_delete_orphan_to_string_expect_all_delete_orphan() -> (
    None
):
    """CascadeOption.ALL | CascadeOption.DELETE_ORPHAN을 문자열로 변환하면 'all, delete-orphan'이 반환되어야 한다."""
    combined = CascadeOption.ALL | CascadeOption.DELETE_ORPHAN

    result = combined.to_string()

    assert result == "all, delete-orphan"


def test_cascade_option_from_string_none_expect_none_flag() -> None:
    """'none' 문자열을 파싱하면 CascadeOption.NONE이 반환되어야 한다."""
    result = CascadeOption.from_string("none")

    assert result == CascadeOption.NONE


def test_cascade_option_from_string_single_flag_expect_correct_flag() -> None:
    """단일 플래그 문자열을 파싱하면 올바른 CascadeOption이 반환되어야 한다."""
    assert CascadeOption.from_string("save-update") == CascadeOption.SAVE_UPDATE
    assert CascadeOption.from_string("merge") == CascadeOption.MERGE
    assert CascadeOption.from_string("delete") == CascadeOption.DELETE
    assert CascadeOption.from_string("delete-orphan") == CascadeOption.DELETE_ORPHAN


def test_cascade_option_from_string_all_delete_orphan_expect_combined_flag() -> None:
    """'all, delete-orphan' 문자열을 파싱하면 ALL | DELETE_ORPHAN이 반환되어야 한다."""
    result = CascadeOption.from_string("all, delete-orphan")

    assert result == CascadeOption.ALL_DELETE_ORPHAN


def test_cascade_option_from_string_combined_expect_correct_flags() -> None:
    """결합된 플래그 문자열을 파싱하면 올바른 CascadeOption 조합이 반환되어야 한다."""
    result = CascadeOption.from_string("save-update, merge")

    assert result & CascadeOption.SAVE_UPDATE
    assert result & CascadeOption.MERGE
    assert not (result & CascadeOption.DELETE)


def test_cascade_option_or_operator_expect_combined_flags() -> None:
    """| 연산자로 CascadeOption을 결합할 수 있어야 한다."""
    combined = CascadeOption.SAVE_UPDATE | CascadeOption.DELETE

    assert combined & CascadeOption.SAVE_UPDATE
    assert combined & CascadeOption.DELETE
    assert not (combined & CascadeOption.MERGE)


def test_cascade_option_roundtrip_expect_preserved() -> None:
    """to_string → from_string 왕복 변환 후에도 값이 보존되어야 한다."""
    original = CascadeOption.SAVE_UPDATE | CascadeOption.MERGE | CascadeOption.DELETE

    result = CascadeOption.from_string(original.to_string())

    # Check individual flags as order may differ
    assert bool(result & CascadeOption.SAVE_UPDATE)
    assert bool(result & CascadeOption.MERGE)
    assert bool(result & CascadeOption.DELETE)


def test_cascade_option_from_string_with_unknown_options_expect_ignored() -> None:
    """알 수 없는 cascade 옵션은 무시되어야 한다."""
    result = CascadeOption.from_string("save-update, unknown-option, delete")

    assert bool(result & CascadeOption.SAVE_UPDATE)
    assert bool(result & CascadeOption.DELETE)
    # unknown-option은 무시됨
    assert result == (CascadeOption.SAVE_UPDATE | CascadeOption.DELETE)
