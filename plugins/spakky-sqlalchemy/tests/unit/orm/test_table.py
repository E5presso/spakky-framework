from datetime import datetime
from typing import Self
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models import AbstractEntity
from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import (
    AbstractMappableTable,
    AbstractTable,
    CannotUseTableAnnotationError,
    Table,
)


def test_table_annotation_with_non_table_classs() -> None:
    """AbstractTable을 상속하지 않은 클래스에 @Table 적용 시 에러 발생 검증."""
    with pytest.raises(CannotUseTableAnnotationError):

        @Table()
        class NotATable:
            pass


def test_table_annotation_with_specified_target_domain() -> None:
    """@Table에 명시적 도메인 타입 지정 시 올바르게 매핑되는지 검증."""

    @mutable
    class User(AbstractEntity[UUID]):
        username: str
        password: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid7()

        def validate(self) -> None:
            return

    @Table(User)
    class UserTable(AbstractMappableTable[User]):
        __tablename__ = "unit_test_users"

        uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
        version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
        username: Mapped[str] = mapped_column(String(), nullable=False)
        password: Mapped[str] = mapped_column(String(), nullable=False)

        @classmethod
        def from_domain(cls, domain: User) -> Self:
            return cls(
                uid=domain.uid,
                username=domain.username,
                password=domain.password,
            )

        def to_domain(self) -> User:
            return User(
                uid=self.uid,
                username=self.username,
                password=self.password,
            )

    assert Table.get(UserTable).domain is User
    assert Table.get(UserTable).table is UserTable
    assert Table.get(UserTable) == Table.get(UserTable)


def test_table_annotation_with_implicit_target_domain() -> None:
    """@Table에 도메인 타입 생략 시 제네릭 파라미터에서 자동 추론되는지 검증."""

    @mutable
    class Member(AbstractEntity[UUID]):
        username: str
        password: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid7()

        def validate(self) -> None:
            return

    @Table()
    class MemberTable(AbstractMappableTable[Member]):
        __tablename__ = "unit_test_members"

        uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
        version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
        username: Mapped[str] = mapped_column(String(), nullable=False)
        password: Mapped[str] = mapped_column(String(), nullable=False)

        @classmethod
        def from_domain(cls, domain: Member) -> Self:
            return cls(
                uid=domain.uid,
                username=domain.username,
                password=domain.password,
            )

        def to_domain(self) -> Member:
            return Member(
                uid=self.uid,
                username=self.username,
                password=self.password,
            )

    assert Table.get(MemberTable).domain is Member
    assert Table.get(MemberTable).table is MemberTable
    assert Table.get(MemberTable) == Table.get(MemberTable)


def test_table_annotation_with_non_mappable_table_expect_domain_none() -> None:
    """AbstractTable을 상속한 non-mappable 테이블에 @Table 적용 시 domain이 None임을 검증."""

    @Table()
    class InfrastructureTable(AbstractTable):
        __tablename__ = "unit_test_infrastructure"

        id: Mapped[int] = mapped_column(primary_key=True)
        data: Mapped[str] = mapped_column(String(), nullable=False)

    table_tag = Table.get(InfrastructureTable)
    assert table_tag.domain is None
    assert table_tag.table is InfrastructureTable
