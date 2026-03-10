"""Tests for AggregateCollector integration with SQLAlchemy Repository."""

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.aggregate_collector import AggregateCollector

from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.apps.models.user import User
from tests.apps.repositories.user import AsyncUserRepository


@pytest.fixture(name="collector")
def collector_fixture(app: SpakkyApplication) -> AggregateCollector:
    """Get AggregateCollector from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AggregateCollector instance.
    """
    return app.container.get(type_=AggregateCollector)


@pytest.fixture(name="user_repository")
def user_repository_fixture(app: SpakkyApplication) -> AsyncUserRepository:
    """Get AsyncUserRepository from application container.

    Args:
        app: SpakkyApplication instance.

    Returns:
        AsyncUserRepository instance.
    """
    return app.container.get(type_=AsyncUserRepository)


@pytest.mark.asyncio
async def test_repository_save_collects_aggregate(
    async_transaction: AsyncTransaction,
    collector: AggregateCollector,
    user_repository: AsyncUserRepository,
    unique_id: str,
) -> None:
    """Repository save()가 AggregateCollector에 aggregate를 등록한다."""
    # Given
    user = User.create(
        username=f"test_collector_user_{unique_id}",
        email=f"test_{unique_id}@example.com",
        password_hash="hash123",
    )
    collector.clear()

    # When
    async with async_transaction:
        await user_repository.save(user)

        # Then
        collected = collector.all()
        assert len(collected) == 1
        assert collected[0].uid == user.uid


@pytest.mark.asyncio
async def test_repository_save_all_collects_all_aggregates(
    async_transaction: AsyncTransaction,
    collector: AggregateCollector,
    user_repository: AsyncUserRepository,
    unique_id: str,
) -> None:
    """Repository save_all()이 모든 aggregate를 AggregateCollector에 등록한다."""
    # Given
    users = [
        User.create(
            username=f"test_collector_user_{unique_id}_{i}",
            email=f"test_{unique_id}_{i}@example.com",
            password_hash=f"hash{i}",
        )
        for i in range(3)
    ]
    collector.clear()

    # When
    async with async_transaction:
        await user_repository.save_all(users)

        # Then
        collected = collector.all()
        assert len(collected) == 3
        collected_uids = {a.uid for a in collected}
        for user in users:
            assert user.uid in collected_uids


@pytest.mark.asyncio
async def test_repository_delete_collects_aggregate(
    async_transaction: AsyncTransaction,
    collector: AggregateCollector,
    user_repository: AsyncUserRepository,
    unique_id: str,
) -> None:
    """Repository delete()도 AggregateCollector에 aggregate를 등록한다 (삭제 이벤트 지원)."""
    # Given
    user = User.create(
        username=f"test_delete_collector_user_{unique_id}",
        email=f"delete_test_{unique_id}@example.com",
        password_hash="hash123",
    )
    async with async_transaction:
        await user_repository.save(user)

    collector.clear()

    # When
    async with async_transaction:
        await user_repository.delete(user)

        # Then
        collected = collector.all()
        assert len(collected) == 1
        assert collected[0].uid == user.uid


@pytest.mark.asyncio
async def test_repository_delete_all_collects_all_aggregates(
    async_transaction: AsyncTransaction,
    collector: AggregateCollector,
    user_repository: AsyncUserRepository,
    unique_id: str,
) -> None:
    """Repository delete_all()이 모든 aggregate를 AggregateCollector에 등록한다."""
    # Given
    users = [
        User.create(
            username=f"test_delete_all_user_{unique_id}_{i}",
            email=f"delete_{unique_id}_{i}@example.com",
            password_hash=f"hash{i}",
        )
        for i in range(2)
    ]
    async with async_transaction:
        await user_repository.save_all(users)

    collector.clear()

    # When
    async with async_transaction:
        await user_repository.delete_all(users)

        # Then
        collected = collector.all()
        assert len(collected) == 2
        collected_uids = {a.uid for a in collected}
        for user in users:
            assert user.uid in collected_uids


@pytest.mark.asyncio
async def test_collector_clear_removes_all_aggregates(
    async_transaction: AsyncTransaction,
    collector: AggregateCollector,
    user_repository: AsyncUserRepository,
    unique_id: str,
) -> None:
    """AggregateCollector clear()가 모든 수집된 aggregate를 제거한다."""
    # Given
    user = User.create(
        username=f"test_clear_user_{unique_id}",
        email=f"clear_test_{unique_id}@example.com",
        password_hash="hash123",
    )

    async with async_transaction:
        await user_repository.save(user)
        assert len(collector.all()) > 0

        # When
        collector.clear()

        # Then
        assert len(collector.all()) == 0
