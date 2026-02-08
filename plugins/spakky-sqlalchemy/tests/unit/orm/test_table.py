"""Tests for Table annotation."""

from dataclasses import dataclass

import pytest
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.sqlalchemy.orm.table import Table


def test_table_with_auto_generated_name_expect_snake_case() -> None:
    """Table annotation 적용 시 클래스 이름으로부터 snake_case 테이블명이 자동 생성되는지 검증한다."""

    @Table()
    @dataclass
    class UserAccount:
        id: int
        username: str

    annotation = Table.get(UserAccount)
    assert annotation.table_name == "user_account"


def test_table_with_custom_name_expect_custom_name_preserved() -> None:
    """Table annotation에 table_name을 직접 지정하면 해당 이름이 그대로 사용되는지 검증한다."""

    @Table(table_name="custom_users")
    @dataclass
    class User:
        id: int

    annotation = Table.get(User)
    assert annotation.table_name == "custom_users"


def test_table_with_single_word_class_expect_lowercase() -> None:
    """단일 단어 클래스 이름에 대해 소문자 테이블명이 생성되는지 검증한다."""

    @Table()
    @dataclass
    class Order:
        id: int

    annotation = Table.get(Order)
    assert annotation.table_name == "order"


def test_table_applied_to_non_dataclass_expect_type_error() -> None:
    """Table annotation이 dataclass가 아닌 클래스에 적용되면 TypeError가 발생하는지 검증한다."""

    with pytest.raises(
        TypeError, match="Table annotation can only be applied to dataclass types."
    ):

        @Table()
        class NotADataclass:
            id: int


def test_table_exists_on_annotated_class_expect_true() -> None:
    """Table annotation이 적용된 클래스에서 exists()가 True를 반환하는지 검증한다."""

    @Table()
    @dataclass
    class Product:
        id: int

    assert Table.exists(Product) is True


def test_table_exists_on_plain_class_expect_false() -> None:
    """Table annotation이 없는 클래스에서 exists()가 False를 반환하는지 검증한다."""

    @dataclass
    class PlainClass:
        id: int

    assert Table.exists(PlainClass) is False


def test_table_with_multi_word_class_expect_correct_snake_case() -> None:
    """여러 단어로 구성된 클래스 이름에서 올바른 snake_case가 생성되는지 검증한다."""

    @Table()
    @dataclass
    class UserAccountSettings:
        id: int

    annotation = Table.get(UserAccountSettings)
    assert annotation.table_name == "user_account_settings"


def test_table_with_empty_name_string_expect_auto_generated() -> None:
    """table_name을 빈 문자열로 명시해도 자동 생성되는지 검증한다."""

    @Table(table_name="")
    @dataclass
    class Employee:
        id: int

    annotation = Table.get(Employee)
    assert annotation.table_name == "employee"


def test_table_get_annotation_expect_table_instance() -> None:
    """Table.get()으로 반환된 객체가 Table 인스턴스인지 검증한다."""

    @Table()
    @dataclass
    class Category:
        id: int

    annotation = Table.get(Category)
    assert isinstance(annotation, Table)


def test_table_all_annotations_expect_single_element_list() -> None:
    """Table.all()이 하나의 Table 인스턴스를 포함한 리스트를 반환하는지 검증한다."""

    @Table()
    @dataclass
    class Tag:
        id: int

    annotations = Table.all(Tag)
    assert len(annotations) == 1
    assert isinstance(annotations[0], Table)


def test_table_get_or_none_on_annotated_expect_table() -> None:
    """Table.get_or_none()이 어노테이션이 있을 때 Table을 반환하는지 검증한다."""

    @Table(table_name="items")
    @dataclass
    class Item:
        id: int

    result = Table.get_or_none(Item)
    assert result is not None
    assert result.table_name == "items"


def test_table_get_or_none_on_plain_expect_none() -> None:
    """Table.get_or_none()이 어노테이션이 없을 때 None을 반환하는지 검증한다."""

    @dataclass
    class PlainItem:
        id: int

    result = Table.get_or_none(PlainItem)
    assert result is None


def test_table_is_pod_annotation_expect_true() -> None:
    """Table이 Pod를 상속하는지 검증한다."""

    @Table()
    @dataclass
    class TestEntity:
        id: int

    assert Pod.exists(TestEntity) is True
    assert Table.exists(TestEntity) is True


def test_table_has_definition_scope_expect_true() -> None:
    """Table annotation이 DEFINITION 스코프를 가지는지 검증한다."""

    @Table()
    @dataclass
    class TestEntity:
        id: int

    annotation = Table.get(TestEntity)
    assert annotation.scope == Pod.Scope.DEFINITION


def test_table_pod_name_auto_generated_expect_snake_case() -> None:
    """Table의 Pod name이 자동으로 snake_case로 생성되는지 검증한다."""

    @Table()
    @dataclass
    class MyTestEntity:
        id: int

    annotation = Table.get(MyTestEntity)
    # Pod.name is auto-generated from class name
    assert annotation.name == "my_test_entity"
