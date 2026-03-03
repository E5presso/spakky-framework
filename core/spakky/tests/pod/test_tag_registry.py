"""Tests for TagRegistry functionality in ApplicationContext.

This module tests the ITagRegistry interface implementation in ApplicationContext,
including tag registration, lookup, and filtering.
"""

from dataclasses import dataclass

from spakky.core.application.application_context import ApplicationContext
from spakky.core.pod.annotations.tag import Tag


@dataclass(eq=False)
class CustomTag(Tag):
    """Custom tag for testing."""

    value: str = ""


@dataclass(eq=False)
class AnotherTag(Tag):
    """Another custom tag for testing."""

    category: str = ""


def test_tags_property_returns_empty_frozenset_initially_expect_empty() -> None:
    """tags 프로퍼티가 태그가 등록되지 않았을 때 빈 frozenset을 반환함을 검증한다."""
    context = ApplicationContext()

    result = context.tags

    assert result == frozenset()
    assert isinstance(result, frozenset)


def test_register_tag_single_tag_expect_tag_registered() -> None:
    """register_tag가 단일 태그를 레지스트리에 추가함을 검증한다."""
    context = ApplicationContext()
    tag = CustomTag(value="test")

    context.register_tag(tag)

    assert tag in context.tags
    assert len(context.tags) == 1


def test_register_tag_multiple_tags_expect_all_registered() -> None:
    """register_tag가 여러 다른 태그를 모두 등록할 수 있음을 검증한다."""
    context = ApplicationContext()
    tag1 = CustomTag(value="first")
    tag2 = CustomTag(value="second")
    tag3 = AnotherTag(category="category1")

    context.register_tag(tag1)
    context.register_tag(tag2)
    context.register_tag(tag3)

    assert len(context.tags) == 3
    assert tag1 in context.tags
    assert tag2 in context.tags
    assert tag3 in context.tags


def test_register_tag_duplicate_tag_expect_no_duplicate() -> None:
    """동일한 태그를 두 번 등록해도 중복이 생기지 않음을 검증한다."""
    context = ApplicationContext()
    tag1 = CustomTag(value="test")
    tag2 = CustomTag(value="test")  # Same values = equal tags

    context.register_tag(tag1)
    context.register_tag(tag2)

    assert len(context.tags) == 1


def test_contains_tag_registered_tag_expect_true() -> None:
    """contains_tag가 등록된 태그에 대해 True를 반환함을 검증한다."""
    context = ApplicationContext()
    tag = CustomTag(value="test")
    context.register_tag(tag)

    result = context.contains_tag(tag)

    assert result is True


def test_contains_tag_equal_tag_expect_true() -> None:
    """contains_tag가 동일한 값을 가진 다른 인스턴스에 대해서도 True를 반환함을 검증한다."""
    context = ApplicationContext()
    tag1 = CustomTag(value="test")
    tag2 = CustomTag(value="test")  # Different instance, same values
    context.register_tag(tag1)

    result = context.contains_tag(tag2)

    assert result is True


def test_contains_tag_unregistered_tag_expect_false() -> None:
    """contains_tag가 등록되지 않은 태그에 대해 False를 반환함을 검증한다."""
    context = ApplicationContext()
    registered_tag = CustomTag(value="registered")
    unregistered_tag = CustomTag(value="unregistered")
    context.register_tag(registered_tag)

    result = context.contains_tag(unregistered_tag)

    assert result is False


def test_contains_tag_empty_registry_expect_false() -> None:
    """contains_tag가 레지스트리가 비어있을 때 False를 반환함을 검증한다."""
    context = ApplicationContext()
    tag = CustomTag(value="test")

    result = context.contains_tag(tag)

    assert result is False


def test_list_tags_no_selector_expect_all_tags() -> None:
    """list_tags가 selector 없이 호출될 때 모든 등록된 태그를 반환함을 검증한다."""
    context = ApplicationContext()
    tag1 = CustomTag(value="first")
    tag2 = CustomTag(value="second")
    tag3 = AnotherTag(category="category1")
    context.register_tag(tag1)
    context.register_tag(tag2)
    context.register_tag(tag3)

    result = context.list_tags()

    assert result == frozenset({tag1, tag2, tag3})
    assert isinstance(result, frozenset)


def test_list_tags_with_selector_expect_filtered_tags() -> None:
    """list_tags가 selector를 사용하여 일치하는 태그만 반환함을 검증한다."""
    context = ApplicationContext()
    tag1 = CustomTag(value="apple")
    tag2 = CustomTag(value="banana")
    tag3 = CustomTag(value="apricot")
    context.register_tag(tag1)
    context.register_tag(tag2)
    context.register_tag(tag3)

    result = context.list_tags(
        lambda t: isinstance(t, CustomTag) and t.value.startswith("ap")
    )

    assert len(result) == 2
    assert tag1 in result
    assert tag3 in result
    assert tag2 not in result


def test_list_tags_selector_by_type_expect_type_filtered() -> None:
    """list_tags가 타입별로 태그를 필터링할 수 있음을 검증한다."""
    context = ApplicationContext()
    custom1 = CustomTag(value="custom1")
    custom2 = CustomTag(value="custom2")
    another = AnotherTag(category="cat1")
    context.register_tag(custom1)
    context.register_tag(custom2)
    context.register_tag(another)

    result = context.list_tags(lambda t: isinstance(t, CustomTag))

    assert len(result) == 2
    assert custom1 in result
    assert custom2 in result
    assert another not in result


def test_list_tags_selector_no_match_expect_empty() -> None:
    """list_tags가 일치하는 태그가 없을 때 빈 frozenset을 반환함을 검증한다."""
    context = ApplicationContext()
    tag = CustomTag(value="test")
    context.register_tag(tag)

    result = context.list_tags(lambda t: False)

    assert result == frozenset()


def test_list_tags_empty_registry_expect_empty() -> None:
    """list_tags가 레지스트리가 비어있을 때 빈 frozenset을 반환함을 검증한다."""
    context = ApplicationContext()

    result = context.list_tags()

    assert result == frozenset()


def test_tags_property_immutability_expect_frozenset() -> None:
    """tags 프로퍼티가 불변의 frozenset을 반환함을 검증한다."""
    context = ApplicationContext()
    tag = CustomTag(value="test")
    context.register_tag(tag)

    tags = context.tags

    assert isinstance(tags, frozenset)
    # frozenset은 불변이므로 add/remove 메서드가 없음
    assert not hasattr(tags, "add")
    assert not hasattr(tags, "remove")


# --- Tag class tests ---


def test_tag_eq_same_instance_expect_true() -> None:
    """Tag의 __eq__가 동일한 인스턴스에 대해 True를 반환함을 검증한다."""
    tag = CustomTag(value="test")

    result = tag == tag

    assert result is True


def test_tag_eq_non_tag_object_expect_false() -> None:
    """Tag의 __eq__가 Tag가 아닌 객체와 비교 시 False를 반환함을 검증한다."""
    tag = CustomTag(value="test")

    result = tag == "not a tag"

    assert result is False


def test_tag_eq_none_expect_false() -> None:
    """Tag의 __eq__가 None과 비교 시 False를 반환함을 검증한다."""
    tag = CustomTag(value="test")

    result = tag == None  # noqa: E711

    assert result is False


def test_tag_eq_different_values_expect_false() -> None:
    """Tag의 __eq__가 다른 값을 가진 태그에 대해 False를 반환함을 검증한다."""
    tag1 = CustomTag(value="first")
    tag2 = CustomTag(value="second")

    result = tag1 == tag2

    assert result is False


def test_tag_hash_equal_tags_expect_same_hash() -> None:
    """동일한 태그가 같은 해시값을 가짐을 검증한다."""
    tag1 = CustomTag(value="test")
    tag2 = CustomTag(value="test")

    assert hash(tag1) == hash(tag2)


def test_tag_hash_different_tags_expect_different_hash() -> None:
    """다른 태그가 다른 해시값을 가짐을 검증한다."""
    tag1 = CustomTag(value="first")
    tag2 = CustomTag(value="second")

    assert hash(tag1) != hash(tag2)
