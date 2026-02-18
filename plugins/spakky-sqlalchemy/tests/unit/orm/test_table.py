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
    AbstractTable,
    CannotUseTableAnnotationError,
    Table,
)


def test_table_annotation_with_non_table_class_expect_error() -> None:
    with pytest.raises(CannotUseTableAnnotationError):

        @Table()
        class NotATable:
            pass


def test_table_annotation_with_specified_target_domain() -> None:
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
    class UserTable(AbstractTable[User]):
        __tablename__ = "users"

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

    assert Table.get(UserTable).target_domain == User


def test_table_annotation_with_implicit_target_domain() -> None:
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
    class MemberTable(AbstractTable[Member]):
        __tablename__ = "members"

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

    assert Table.get(MemberTable).target_domain == Member
