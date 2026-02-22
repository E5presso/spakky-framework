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
    """Test that tags property returns empty frozenset when no tags registered."""
    context = ApplicationContext()

    result = context.tags

    assert result == frozenset()
    assert isinstance(result, frozenset)


def test_register_tag_single_tag_expect_tag_registered() -> None:
    """Test that register_tag adds a single tag to the registry."""
    context = ApplicationContext()
    tag = CustomTag(value="test")

    context.register_tag(tag)

    assert tag in context.tags
    assert len(context.tags) == 1


def test_register_tag_multiple_tags_expect_all_registered() -> None:
    """Test that register_tag can add multiple different tags."""
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
    """Test that registering the same tag twice doesn't create duplicates."""
    context = ApplicationContext()
    tag1 = CustomTag(value="test")
    tag2 = CustomTag(value="test")  # Same values = equal tags

    context.register_tag(tag1)
    context.register_tag(tag2)

    assert len(context.tags) == 1


def test_contains_tag_registered_tag_expect_true() -> None:
    """Test that contains_tag returns True for registered tags."""
    context = ApplicationContext()
    tag = CustomTag(value="test")
    context.register_tag(tag)

    result = context.contains_tag(tag)

    assert result is True


def test_contains_tag_equal_tag_expect_true() -> None:
    """Test that contains_tag returns True for equal but different tag instance."""
    context = ApplicationContext()
    tag1 = CustomTag(value="test")
    tag2 = CustomTag(value="test")  # Different instance, same values
    context.register_tag(tag1)

    result = context.contains_tag(tag2)

    assert result is True


def test_contains_tag_unregistered_tag_expect_false() -> None:
    """Test that contains_tag returns False for unregistered tags."""
    context = ApplicationContext()
    registered_tag = CustomTag(value="registered")
    unregistered_tag = CustomTag(value="unregistered")
    context.register_tag(registered_tag)

    result = context.contains_tag(unregistered_tag)

    assert result is False


def test_contains_tag_empty_registry_expect_false() -> None:
    """Test that contains_tag returns False when registry is empty."""
    context = ApplicationContext()
    tag = CustomTag(value="test")

    result = context.contains_tag(tag)

    assert result is False


def test_list_tags_no_selector_expect_all_tags() -> None:
    """Test that list_tags without selector returns all registered tags."""
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
    """Test that list_tags with selector returns only matching tags."""
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
    """Test that list_tags can filter by tag type."""
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
    """Test that list_tags with non-matching selector returns empty frozenset."""
    context = ApplicationContext()
    tag = CustomTag(value="test")
    context.register_tag(tag)

    result = context.list_tags(lambda t: False)

    assert result == frozenset()


def test_list_tags_empty_registry_expect_empty() -> None:
    """Test that list_tags returns empty frozenset when registry is empty."""
    context = ApplicationContext()

    result = context.list_tags()

    assert result == frozenset()


def test_tags_property_immutability_expect_frozenset() -> None:
    """Test that tags property returns immutable frozenset."""
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
    """Test that Tag.__eq__ returns True for same instance."""
    tag = CustomTag(value="test")

    result = tag == tag

    assert result is True


def test_tag_eq_non_tag_object_expect_false() -> None:
    """Test that Tag.__eq__ returns False when comparing with non-Tag object."""
    tag = CustomTag(value="test")

    result = tag == "not a tag"

    assert result is False


def test_tag_eq_none_expect_false() -> None:
    """Test that Tag.__eq__ returns False when comparing with None."""
    tag = CustomTag(value="test")

    result = tag == None  # noqa: E711

    assert result is False


def test_tag_eq_different_values_expect_false() -> None:
    """Test that Tag.__eq__ returns False for tags with different values."""
    tag1 = CustomTag(value="first")
    tag2 = CustomTag(value="second")

    result = tag1 == tag2

    assert result is False


def test_tag_hash_equal_tags_expect_same_hash() -> None:
    """Test that equal tags have the same hash."""
    tag1 = CustomTag(value="test")
    tag2 = CustomTag(value="test")

    assert hash(tag1) == hash(tag2)


def test_tag_hash_different_tags_expect_different_hash() -> None:
    """Test that different tags have different hashes."""
    tag1 = CustomTag(value="first")
    tag2 = CustomTag(value="second")

    assert hash(tag1) != hash(tag2)
