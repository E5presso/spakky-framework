from spakky.core.common.importing import is_subpath_of
from tests.dummy.dummy_package import module_a


def test_is_subpath_of_exact_match_expect_true() -> None:
    """정확한 모듈 이름 매치 시 True를 반환함을 검증한다."""
    assert (
        is_subpath_of(
            "tests.dummy.dummy_package.module_a", {"tests.dummy.dummy_package.module_a"}
        )
        is True
    )


def test_is_subpath_of_wildcard_match_expect_true() -> None:
    """와일드카드 패턴 매치 시 True를 반환함을 검증한다."""
    assert (
        is_subpath_of(
            "tests.dummy.dummy_package.module_a", {"tests.dummy.dummy_package.*"}
        )
        is True
    )
    assert (
        is_subpath_of("tests.dummy.dummy_package.module_a", {"tests.*.dummy_package.*"})
        is True
    )


def test_is_subpath_of_prefix_match_expect_true() -> None:
    """접두사 매치(서브모듈) 시 True를 반환함을 검증한다."""
    assert (
        is_subpath_of(
            "tests.dummy.dummy_package.module_a", {"tests.dummy.dummy_package"}
        )
        is True
    )


def test_is_subpath_of_no_match_expect_false() -> None:
    """어떤 패턴과도 매치되지 않으면 False를 반환함을 검증한다."""
    assert (
        is_subpath_of("tests.dummy.dummy_package.module_a", {"other.package"}) is False
    )


def test_is_subpath_of_module_type_input_expect_true() -> None:
    """ModuleType 입력에 대해서도 정상적으로 처리함을 검증한다."""
    assert is_subpath_of(module_a, {module_a}) is True
    assert is_subpath_of(module_a, {"tests.dummy.dummy_package.module_a"}) is True


def test_is_subpath_of_question_mark_wildcard_expect_true() -> None:
    """물음표 와일드카드 패턴 매치 시 True를 반환함을 검증한다."""
    assert (
        is_subpath_of(
            "tests.dummy.dummy_package.module_a", {"tests.dummy.dummy_package.module_?"}
        )
        is True
    )
