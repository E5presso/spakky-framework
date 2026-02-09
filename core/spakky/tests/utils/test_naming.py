"""Tests for naming convention utilities."""

from spakky.core.utils.naming import is_dunder_name, is_private_name, is_public_name


def test_is_dunder_name_with_magic_methods_expect_true() -> None:
    """매직 메서드 이름(__init__, __str__ 등)이 True를 반환하는지 검증한다."""
    assert is_dunder_name("__init__")
    assert is_dunder_name("__str__")
    assert is_dunder_name("__repr__")
    assert is_dunder_name("__eq__")
    assert is_dunder_name("__hash__")
    assert is_dunder_name("__call__")
    assert is_dunder_name("__dataclass_fields__")


def test_is_dunder_name_with_private_prefix_expect_false() -> None:
    """언더스코어로 시작하지만 dunder가 아닌 이름이 False를 반환하는지 검증한다."""
    assert not is_dunder_name("__private")
    assert not is_dunder_name("_internal")
    assert not is_dunder_name("___triple")


def test_is_dunder_name_with_public_names_expect_false() -> None:
    """일반 public 이름이 False를 반환하는지 검증한다."""
    assert not is_dunder_name("public")
    assert not is_dunder_name("username")
    assert not is_dunder_name("")


def test_is_dunder_name_edge_cases_expect_false() -> None:
    """경계 케이스(빈 dunder, 짧은 dunder)가 False를 반환하는지 검증한다."""
    assert not is_dunder_name("____")  # exactly 4 chars
    assert not is_dunder_name("__")
    assert not is_dunder_name("___")


def test_is_public_name_with_regular_names_expect_true() -> None:
    """일반 public 이름이 True를 반환하는지 검증한다."""
    assert is_public_name("username")
    assert is_public_name("UserService")
    assert is_public_name("get_user")
    assert is_public_name("ID")


def test_is_public_name_with_dunder_names_expect_true() -> None:
    """dunder 이름이 public으로 인식되는지 검증한다."""
    assert is_public_name("__init__")
    assert is_public_name("__str__")
    assert is_public_name("__eq__")


def test_is_public_name_with_private_names_expect_false() -> None:
    """private 이름이 False를 반환하는지 검증한다."""
    assert not is_public_name("_internal")
    assert not is_public_name("_events")
    assert not is_public_name("__private")
    assert not is_public_name("__mangled_name")


def test_is_private_name_with_single_underscore_expect_true() -> None:
    """단일 언더스코어로 시작하는 이름이 private으로 인식되는지 검증한다."""
    assert is_private_name("_internal")
    assert is_private_name("_events")
    assert is_private_name("_cache")


def test_is_private_name_with_name_mangled_expect_true() -> None:
    """네임 맹글링 이름(__로 시작, __로 끝나지 않음)이 private으로 인식되는지 검증한다."""
    assert is_private_name("__private")
    assert is_private_name("__mangled")
    assert is_private_name("__secret_value")


def test_is_private_name_with_public_names_expect_false() -> None:
    """public 이름이 False를 반환하는지 검증한다."""
    assert not is_private_name("public")
    assert not is_private_name("username")
    assert not is_private_name("get_user")


def test_is_private_name_with_dunder_names_expect_false() -> None:
    """dunder 이름이 private이 아닌 것으로 인식되는지 검증한다."""
    assert not is_private_name("__init__")
    assert not is_private_name("__str__")
    assert not is_private_name("__dataclass_fields__")
