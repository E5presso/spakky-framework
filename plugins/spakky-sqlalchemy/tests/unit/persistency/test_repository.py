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


# --- Success path tests for sync repository ---


def test_sync_repository_get_success_returns_entity() -> None:
    """Sync get이 entity를 성공적으로 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    expected_entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = expected_entity

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one.return_value = mock_table
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.get(expected_entity.uid)

    assert result == expected_entity


def test_sync_repository_get_not_found_raises_error() -> None:
    """Sync get에서 entity가 없을 때 EntityNotFoundError가 발생하는지 검증한다."""
    from spakky.data.persistency.repository import EntityNotFoundError
    from sqlalchemy.exc import NoResultFound

    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one.side_effect = NoResultFound()
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )

    with pytest.raises(EntityNotFoundError):
        repo.get(uuid7())


def test_sync_repository_get_or_none_found_returns_entity() -> None:
    """Sync get_or_none이 존재하는 entity를 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    expected_entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = expected_entity

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_table
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.get_or_none(expected_entity.uid)

    assert result == expected_entity


def test_sync_repository_get_or_none_not_found_returns_none() -> None:
    """Sync get_or_none이 entity가 없을 때 None을 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.get_or_none(uuid7())

    assert result is None


def test_sync_repository_contains_true() -> None:
    """Sync contains가 entity가 있을 때 True를 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = uuid7()
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.contains(uuid7())

    assert result is True


def test_sync_repository_contains_false() -> None:
    """Sync contains가 entity가 없을 때 False를 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.contains(uuid7())

    assert result is False


def test_sync_repository_range_returns_entities() -> None:
    """Sync range가 여러 entity를 반환하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entities = [
        SampleEntity(
            uid=uuid7(),
            version=uuid7(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            name=f"test{i}",
        )
        for i in range(3)
    ]
    mock_tables = []
    for entity in entities:
        mock_table = MagicMock(spec=SampleEntityTable)
        mock_table.to_domain.return_value = entity
        mock_tables.append(mock_table)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_tables
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_execute_result

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    ids = [e.uid for e in entities]
    results = repo.range(ids)

    assert len(results) == 3
    assert results == entities


def test_sync_repository_save_success() -> None:
    """Sync save가 성공적으로 entity를 저장하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = entity

    mock_schema_registry.from_domain.return_value = mock_table
    mock_session.merge.return_value = mock_table

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.save(entity)

    assert result == entity
    mock_session.merge.assert_called_once()
    mock_session.flush.assert_called_once()
    mock_aggregate_collector.collect.assert_called_once_with(entity)


def test_sync_repository_save_all_success() -> None:
    """Sync save_all이 성공적으로 여러 entity를 저장하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entities = [
        SampleEntity(
            uid=uuid7(),
            version=uuid7(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            name=f"test{i}",
        )
        for i in range(2)
    ]
    mock_tables = []
    for entity in entities:
        mock_table = MagicMock(spec=SampleEntityTable)
        mock_table.to_domain.return_value = entity
        mock_tables.append(mock_table)

    mock_schema_registry.from_domain.side_effect = mock_tables
    mock_session.merge.side_effect = mock_tables

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    results = repo.save_all(entities)

    assert len(results) == 2
    mock_session.flush.assert_called_once()
    assert mock_aggregate_collector.collect.call_count == 2


def test_sync_repository_delete_success() -> None:
    """Sync delete가 성공적으로 entity를 삭제하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = entity

    mock_schema_registry.from_domain.return_value = mock_table
    mock_session.merge.return_value = mock_table

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = repo.delete(entity)

    assert result == entity
    mock_session.delete.assert_called_once_with(mock_table)
    mock_session.flush.assert_called_once()
    mock_aggregate_collector.collect.assert_called_once_with(entity)


def test_sync_repository_delete_all_success() -> None:
    """Sync delete_all이 성공적으로 여러 entity를 삭제하는지 검증한다."""
    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entities = [
        SampleEntity(
            uid=uuid7(),
            version=uuid7(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            name=f"test{i}",
        )
        for i in range(2)
    ]
    mock_tables = []
    for entity in entities:
        mock_table = MagicMock(spec=SampleEntityTable)
        mock_table.to_domain.return_value = entity
        mock_tables.append(mock_table)

    mock_schema_registry.from_domain.side_effect = mock_tables
    mock_session.merge.side_effect = mock_tables

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    results = repo.delete_all(entities)

    assert len(results) == 2
    assert mock_session.delete.call_count == 2
    mock_session.flush.assert_called_once()
    assert mock_aggregate_collector.collect.call_count == 2


# --- Success path tests for async repository ---


@pytest.mark.asyncio
async def test_async_repository_get_success_returns_entity() -> None:
    """Async get이 entity를 성공적으로 반환하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    expected_entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = expected_entity

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one.return_value = mock_table
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.get(expected_entity.uid)

    assert result == expected_entity


@pytest.mark.asyncio
async def test_async_repository_get_not_found_raises_error() -> None:
    """Async get에서 entity가 없을 때 EntityNotFoundError가 발생하는지 검증한다."""
    from unittest.mock import AsyncMock

    from spakky.data.persistency.repository import EntityNotFoundError
    from sqlalchemy.exc import NoResultFound

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one.side_effect = NoResultFound()
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )

    with pytest.raises(EntityNotFoundError):
        await repo.get(uuid7())


@pytest.mark.asyncio
async def test_async_repository_get_or_none_found_returns_entity() -> None:
    """Async get_or_none이 존재하는 entity를 반환하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    expected_entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = expected_entity

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_table
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.get_or_none(expected_entity.uid)

    assert result == expected_entity


@pytest.mark.asyncio
async def test_async_repository_get_or_none_not_found_returns_none() -> None:
    """Async get_or_none이 entity가 없을 때 None을 반환하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.get_or_none(uuid7())

    assert result is None


@pytest.mark.asyncio
async def test_async_repository_contains_true() -> None:
    """Async contains가 entity가 있을 때 True를 반환하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = uuid7()
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.contains(uuid7())

    assert result is True


@pytest.mark.asyncio
async def test_async_repository_contains_false() -> None:
    """Async contains가 entity가 없을 때 False를 반환하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.contains(uuid7())

    assert result is False


@pytest.mark.asyncio
async def test_async_repository_range_returns_entities() -> None:
    """Async range가 여러 entity를 반환하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entities = [
        SampleEntity(
            uid=uuid7(),
            version=uuid7(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            name=f"test{i}",
        )
        for i in range(3)
    ]
    mock_tables = []
    for entity in entities:
        mock_table = MagicMock(spec=SampleEntityTable)
        mock_table.to_domain.return_value = entity
        mock_tables.append(mock_table)

    mock_schema_registry.get_type.return_value = SampleEntityTable
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_tables
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_execute_result)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    ids = [e.uid for e in entities]
    results = await repo.range(ids)

    assert len(results) == 3
    assert results == entities


@pytest.mark.asyncio
async def test_async_repository_save_success() -> None:
    """Async save가 성공적으로 entity를 저장하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = entity

    mock_schema_registry.from_domain.return_value = mock_table
    mock_session.merge = AsyncMock(return_value=mock_table)
    mock_session.flush = AsyncMock()

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.save(entity)

    assert result == entity
    mock_session.merge.assert_awaited_once()
    mock_session.flush.assert_awaited_once()
    mock_aggregate_collector.collect.assert_called_once_with(entity)


@pytest.mark.asyncio
async def test_async_repository_save_all_success() -> None:
    """Async save_all이 성공적으로 여러 entity를 저장하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entities = [
        SampleEntity(
            uid=uuid7(),
            version=uuid7(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            name=f"test{i}",
        )
        for i in range(2)
    ]
    mock_tables = []
    for entity in entities:
        mock_table = MagicMock(spec=SampleEntityTable)
        mock_table.to_domain.return_value = entity
        mock_tables.append(mock_table)

    mock_schema_registry.from_domain.side_effect = mock_tables
    mock_session.merge = AsyncMock(side_effect=mock_tables)
    mock_session.flush = AsyncMock()

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    results = await repo.save_all(entities)

    assert len(results) == 2
    mock_session.flush.assert_awaited_once()
    assert mock_aggregate_collector.collect.call_count == 2


@pytest.mark.asyncio
async def test_async_repository_delete_success() -> None:
    """Async delete가 성공적으로 entity를 삭제하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entity = SampleEntity(
        uid=uuid7(),
        version=uuid7(),
        created_at=datetime.now(),
        updated_at=datetime.now(),
        name="test",
    )
    mock_table = MagicMock(spec=SampleEntityTable)
    mock_table.to_domain.return_value = entity

    mock_schema_registry.from_domain.return_value = mock_table
    mock_session.merge = AsyncMock(return_value=mock_table)
    mock_session.delete = AsyncMock()
    mock_session.flush = AsyncMock()

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    result = await repo.delete(entity)

    assert result == entity
    mock_session.delete.assert_awaited_once_with(mock_table)
    mock_session.flush.assert_awaited_once()
    mock_aggregate_collector.collect.assert_called_once_with(entity)


@pytest.mark.asyncio
async def test_async_repository_delete_all_success() -> None:
    """Async delete_all이 성공적으로 여러 entity를 삭제하는지 검증한다."""
    from unittest.mock import AsyncMock

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)
    mock_session = MagicMock()
    type(mock_session_manager).session = PropertyMock(return_value=mock_session)

    entities = [
        SampleEntity(
            uid=uuid7(),
            version=uuid7(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            name=f"test{i}",
        )
        for i in range(2)
    ]
    mock_tables = []
    for entity in entities:
        mock_table = MagicMock(spec=SampleEntityTable)
        mock_table.to_domain.return_value = entity
        mock_tables.append(mock_table)

    mock_schema_registry.from_domain.side_effect = mock_tables
    mock_session.merge = AsyncMock(side_effect=mock_tables)
    mock_session.delete = AsyncMock()
    mock_session.flush = AsyncMock()

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )
    results = await repo.delete_all(entities)

    assert len(results) == 2
    assert mock_session.delete.await_count == 2
    mock_session.flush.assert_awaited_once()
    assert mock_aggregate_collector.collect.call_count == 2


# --- Composite PK tests ---


def test_sync_repository_build_pk_condition_with_composite_pk() -> None:
    """복합 PK에서 _build_pk_condition이 올바른 조건을 생성하는지 검증한다."""
    from sqlalchemy import Column, Integer

    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )

    # 복합 PK 컬럼 생성 (2개 컬럼)
    col1 = Column("id1", Integer, primary_key=True)
    col2 = Column("id2", Integer, primary_key=True)
    pk_columns = [col1, col2]
    aggregate_id = (1, 2)

    condition = repo._build_pk_condition(pk_columns, aggregate_id)

    # and_ 조건이 올바르게 생성되었는지 확인
    assert condition is not None
    assert str(condition) == "id1 = :id1_1 AND id2 = :id2_1"


def test_sync_repository_build_pk_in_condition_with_composite_pk() -> None:
    """복합 PK에서 _build_pk_in_condition이 올바른 조건을 생성하는지 검증한다."""
    from sqlalchemy import Column, Integer

    mock_session_manager = MagicMock(spec=SessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)

    repo = ValidSyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )

    # 복합 PK 컬럼 생성 (2개 컬럼)
    col1 = Column("id1", Integer, primary_key=True)
    col2 = Column("id2", Integer, primary_key=True)
    pk_columns = [col1, col2]
    aggregate_ids = [(1, 2), (3, 4)]

    condition = repo._build_pk_in_condition(pk_columns, aggregate_ids)

    # tuple_ IN 조건이 올바르게 생성되었는지 확인
    assert condition is not None
    assert "(id1, id2) IN" in str(condition)


@pytest.mark.asyncio
async def test_async_repository_build_pk_condition_with_composite_pk() -> None:
    """async 복합 PK에서 _build_pk_condition이 올바른 조건을 생성하는지 검증한다."""
    from sqlalchemy import Column, Integer

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )

    # 복합 PK 컬럼 생성 (2개 컬럼)
    col1 = Column("id1", Integer, primary_key=True)
    col2 = Column("id2", Integer, primary_key=True)
    pk_columns = [col1, col2]
    aggregate_id = (1, 2)

    condition = repo._build_pk_condition(pk_columns, aggregate_id)

    # and_ 조건이 올바르게 생성되었는지 확인
    assert condition is not None
    assert str(condition) == "id1 = :id1_1 AND id2 = :id2_1"


@pytest.mark.asyncio
async def test_async_repository_build_pk_in_condition_with_composite_pk() -> None:
    """async 복합 PK에서 _build_pk_in_condition이 올바른 조건을 생성하는지 검증한다."""
    from sqlalchemy import Column, Integer

    mock_session_manager = MagicMock(spec=AsyncSessionManager)
    mock_schema_registry = MagicMock(spec=SchemaRegistry)
    mock_aggregate_collector = MagicMock(spec=AggregateCollector)

    repo = ValidAsyncRepository(
        mock_session_manager, mock_schema_registry, mock_aggregate_collector
    )

    # 복합 PK 컬럼 생성 (2개 컬럼)
    col1 = Column("id1", Integer, primary_key=True)
    col2 = Column("id2", Integer, primary_key=True)
    pk_columns = [col1, col2]
    aggregate_ids = [(1, 2), (3, 4)]

    condition = repo._build_pk_in_condition(pk_columns, aggregate_ids)

    # tuple_ IN 조건이 올바르게 생성되었는지 확인
    assert condition is not None
    assert "(id1, id2) IN" in str(condition)
