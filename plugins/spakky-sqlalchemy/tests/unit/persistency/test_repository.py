"""Unit tests for repository error conditions."""

from datetime import datetime
from typing import Self
from unittest.mock import MagicMock, PropertyMock
from uuid import UUID

import pytest
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.data.persistency.aggregate_collector import AggregateCollector
from spakky.data.persistency.repository import VersionConflictError
from spakky.domain.models.aggregate_root import AbstractAggregateRoot
from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.exc import StaleDataError

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table
from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
    CannotDetermineAggregateTypeError,
)
from spakky.plugins.sqlalchemy.persistency.session_manager import (
    AsyncSessionManager,
    SessionManager,
)


@mutable
class SampleEntity(AbstractAggregateRoot[UUID]):
    """Test domain entity."""

    name: str

    @classmethod
    def next_id(cls) -> UUID:
        return uuid7()

    def validate(self) -> None:
        pass


@Table(SampleEntity)
class SampleEntityTable(AbstractMappableTable[SampleEntity]):
    """Test table."""

    __tablename__ = "test_entities"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    name: Mapped[str] = mapped_column(String(), nullable=False)

    @classmethod
    def from_domain(cls, domain: SampleEntity) -> Self:
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            name=domain.name,
        )

    def to_domain(self) -> SampleEntity:
        return SampleEntity(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            name=self.name,
        )


class InvalidSyncRepository(AbstractGenericRepository):
    """Repository without proper generic parameters."""

    pass


class InvalidAsyncRepository(AbstractAsyncGenericRepository):
    """Async repository without proper generic parameters."""

    pass


def test_sync_repository_without_generic_params_expect_error() -> None:
    """Generic 파라미터 없이 sync repository 생성 시 에러가 발생한다."""
    # Mock objects (None은 실제로 사용되지 않음 - __init__에서 에러 발생)
    session_manager = None
    schema_registry = None
    aggregate_collector = None

    with pytest.raises(CannotDetermineAggregateTypeError):
        InvalidSyncRepository(session_manager, schema_registry, aggregate_collector)  # type: ignore


def test_async_repository_without_generic_params_expect_error() -> None:
    """Generic 파라미터 없이 async repository 생성 시 에러가 발생한다."""
    # Mock objects (None은 실제로 사용되지 않음 - __init__에서 에러 발생)
    session_manager = None
    schema_registry = None
    aggregate_collector = None

    with pytest.raises(CannotDetermineAggregateTypeError):
        InvalidAsyncRepository(session_manager, schema_registry, aggregate_collector)  # type: ignore


# --- Valid repository for version conflict testing ---


class ValidSyncRepository(AbstractGenericRepository[SampleEntity, UUID]):
    """Valid sync repository with proper generic parameters."""

    pass


class ValidAsyncRepository(AbstractAsyncGenericRepository[SampleEntity, UUID]):
    """Valid async repository with proper generic parameters."""

    pass


# --- VersionConflictError tests for sync repository ---


def test_sync_repository_save_stale_data_expect_version_conflict_error() -> None:
    """Sync save에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        repo.save(entity)


def test_sync_repository_save_all_stale_data_expect_version_conflict_error() -> None:
    """Sync save_all에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        repo.save_all([entity])


def test_sync_repository_delete_stale_data_expect_version_conflict_error() -> None:
    """Sync delete에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        repo.delete(entity)


def test_sync_repository_delete_all_stale_data_expect_version_conflict_error() -> None:
    """Sync delete_all에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        repo.delete_all([entity])


# --- VersionConflictError tests for async repository ---


@pytest.mark.asyncio
async def test_async_repository_save_stale_data_expect_version_conflict_error() -> None:
    """Async save에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        await repo.save(entity)


@pytest.mark.asyncio
async def test_async_repository_save_all_stale_data_expect_version_conflict_error() -> (
    None
):
    """Async save_all에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        await repo.save_all([entity])


@pytest.mark.asyncio
async def test_async_repository_delete_stale_data_expect_version_conflict_error() -> (
    None
):
    """Async delete에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        await repo.delete(entity)


@pytest.mark.asyncio
async def test_async_repository_delete_all_stale_data_expect_version_conflict_error() -> (
    None
):
    """Async delete_all에서 StaleDataError 발생 시 VersionConflictError로 변환된다."""
    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    # StaleDataError를 merge에서 발생시킴
    mock_session.merge.side_effect = StaleDataError("Version conflict")

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )

    with pytest.raises(VersionConflictError):
        await repo.delete_all([entity])
