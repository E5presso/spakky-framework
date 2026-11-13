from datetime import datetime
from typing import Any, Self
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models import AbstractEntity
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from sqlalchemy import DateTime, String, Uuid, inspect
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


def test_mappable_table_of_aggregate_without_version_column_expect_no_version_check() -> (
    None
):
    """version 컬럼이 없는 애그리거트 테이블은 version_id_col 없이 매핑된다."""

    @mutable
    class Ledger(AbstractAggregateRoot[UUID]):
        title: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid7()

    @Table(Ledger)
    class LedgerTable(AbstractMappableTable[Ledger]):
        __tablename__ = "unit_test_ledgers_without_version"

        uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
        title: Mapped[str] = mapped_column(String(), nullable=False)

        @classmethod
        def from_domain(cls, domain: Ledger) -> Self:
            return cls(uid=domain.uid, title=domain.title)

        def to_domain(self) -> Ledger:
            return Ledger(uid=self.uid, title=self.title)

    assert inspect(LedgerTable).version_id_col is None


def test_mappable_table_of_aggregate_with_version_column_expect_version_check() -> None:
    """version 컬럼이 있는 애그리거트 테이블은 generator 없는 version_id_col로 매핑된다."""

    @mutable
    class Wallet(AbstractAggregateRoot[UUID]):
        owner: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid7()

    @Table(Wallet)
    class WalletTable(AbstractMappableTable[Wallet]):
        __tablename__ = "unit_test_wallets_with_version"

        uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
        version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
        owner: Mapped[str] = mapped_column(String(), nullable=False)

        @classmethod
        def from_domain(cls, domain: Wallet) -> Self:
            return cls(uid=domain.uid, version=domain.version, owner=domain.owner)

        def to_domain(self) -> Wallet:
            return Wallet(uid=self.uid, version=self.version, owner=self.owner)

    mapper = inspect(WalletTable)
    assert mapper.version_id_col is WalletTable.__table__.c.version
    assert mapper.version_id_generator is False


def test_mappable_table_with_own_versioned_mapper_args_expect_version_check_kept() -> (
    None
):
    """자체 __mapper_args__에 version_id_col을 직접 지정하면 version 검사가 유지된다."""

    @mutable
    class Parcel(AbstractAggregateRoot[UUID]):
        label: str

        @classmethod
        def next_id(cls) -> UUID:
            return uuid7()

    @Table(Parcel)
    class ParcelTable(AbstractMappableTable[Parcel]):
        __tablename__ = "unit_test_parcels_with_own_mapper_args"

        uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
        version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
        label: Mapped[str] = mapped_column(String(), nullable=False)

        # Any: SQLAlchemy mapper kwargs
        __mapper_args__: dict[str, Any] = {
            "version_id_col": version,
            "version_id_generator": False,
            "eager_defaults": True,
        }

        @classmethod
        def from_domain(cls, domain: Parcel) -> Self:
            return cls(uid=domain.uid, version=domain.version, label=domain.label)

        def to_domain(self) -> Parcel:
            return Parcel(uid=self.uid, version=self.version, label=self.label)

    mapper = inspect(ParcelTable)
    assert mapper.version_id_col is ParcelTable.__table__.c.version
    assert mapper.version_id_generator is False
    assert mapper.eager_defaults is True
