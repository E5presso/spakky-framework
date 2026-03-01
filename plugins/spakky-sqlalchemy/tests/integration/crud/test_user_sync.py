"""User entity sync CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import Transaction
from tests.apps.models.user import User


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[User, UUID]:
    """Get sync User repository from application container."""
    return app.container.get(type_=IGenericRepository[User, UUID])


def test_user_save_expect_persisted(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """새 User를 save하면 데이터베이스에 영속화된다."""
    user = User.create(
        username="sync_testuser",
        email="sync_test@example.com",
        password_hash="hashed_password",
    )

    with transaction:
        saved_user = user_repository.save(user)

        assert saved_user.uid == user.uid
        assert saved_user.username == "sync_testuser"
        assert saved_user.email == "sync_test@example.com"


def test_user_save_all_expect_all_persisted(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """여러 User를 save_all하면 모두 영속화된다."""
    users = [
        User.create(
            username=f"sync_user_{i}",
            email=f"sync_user_{i}@example.com",
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]

    with transaction:
        saved_users = user_repository.save_all(users)

        assert len(saved_users) == 3
        for i, saved_user in enumerate(saved_users):
            assert saved_user.uid == users[i].uid


def test_user_get_existing_expect_returned(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 User를 get하면 해당 엔티티가 반환된다."""
    user = User.create(
        username="sync_findme",
        email="sync_findme@example.com",
        password_hash="hashed",
    )

    with transaction:
        user_repository.save(user)
        retrieved_user = user_repository.get(user.uid)

        assert retrieved_user.uid == user.uid
        assert retrieved_user.username == "sync_findme"
        assert retrieved_user.email == "sync_findme@example.com"


def test_user_get_nonexistent_expect_entity_not_found_error(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하지 않는 User를 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_id = uuid4()

    with transaction:
        with pytest.raises(EntityNotFoundError) as exc_info:
            user_repository.get(nonexistent_id)

        assert exc_info.value.args[0] == nonexistent_id


def test_user_get_or_none_existing_expect_returned(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 User를 get_or_none하면 해당 엔티티가 반환된다."""
    user = User.create(
        username="sync_nullable_find",
        email="sync_nullable@example.com",
        password_hash="hashed",
    )

    with transaction:
        user_repository.save(user)
        retrieved_user = user_repository.get_or_none(user.uid)

        assert retrieved_user is not None
        assert retrieved_user.uid == user.uid


def test_user_get_or_none_nonexistent_expect_none(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하지 않는 User를 get_or_none하면 None이 반환된다."""
    nonexistent_id = uuid4()

    with transaction:
        retrieved_user = user_repository.get_or_none(nonexistent_id)

        assert retrieved_user is None


def test_user_contains_existing_expect_true(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 User ID로 contains하면 True가 반환된다."""
    user = User.create(
        username="sync_exists_check",
        email="sync_exists@example.com",
        password_hash="hashed",
    )

    with transaction:
        user_repository.save(user)
        exists = user_repository.contains(user.uid)

        assert exists is True


def test_user_contains_nonexistent_expect_false(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하지 않는 User ID로 contains하면 False가 반환된다."""
    nonexistent_id = uuid4()

    with transaction:
        exists = user_repository.contains(nonexistent_id)

        assert exists is False


def test_user_range_existing_expect_all_returned(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """여러 User ID로 range하면 해당 엔티티들이 반환된다."""
    users = [
        User.create(
            username=f"sync_range_user_{i}",
            email=f"sync_range_{i}@example.com",
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]
    user_ids = [user.uid for user in users]

    with transaction:
        user_repository.save_all(users)
        retrieved_users = user_repository.range(user_ids)

        assert len(retrieved_users) == 3
        retrieved_ids = {user.uid for user in retrieved_users}
        assert retrieved_ids == set(user_ids)


def test_user_range_partial_existing_expect_only_existing_returned(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """일부만 존재하는 ID로 range하면 존재하는 것만 반환된다."""
    user = User.create(
        username="sync_partial_range",
        email="sync_partial@example.com",
        password_hash="hashed",
    )
    nonexistent_id = uuid4()

    with transaction:
        user_repository.save(user)
        retrieved_users = user_repository.range([user.uid, nonexistent_id])

        assert len(retrieved_users) == 1
        assert retrieved_users[0].uid == user.uid


def test_user_range_empty_list_expect_empty_result(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """빈 ID 목록으로 range하면 빈 결과가 반환된다."""
    with transaction:
        retrieved_users = user_repository.range([])

        assert len(retrieved_users) == 0


def test_user_delete_existing_expect_removed(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 User를 delete하면 데이터베이스에서 제거된다."""
    user = User.create(
        username="sync_to_delete",
        email="sync_delete@example.com",
        password_hash="hashed",
    )

    with transaction:
        user_repository.save(user)
        deleted_user = user_repository.delete(user)

        assert deleted_user.uid == user.uid
        assert user_repository.contains(user.uid) is False


def test_user_delete_all_expect_all_removed(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """여러 User를 delete_all하면 모두 제거된다."""
    users = [
        User.create(
            username=f"sync_delete_all_{i}",
            email=f"sync_delete_all_{i}@example.com",
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]

    with transaction:
        user_repository.save_all(users)
        deleted_users = user_repository.delete_all(users)

        assert len(deleted_users) == 3
        for user in users:
            assert user_repository.contains(user.uid) is False


def test_user_save_updated_expect_changes_persisted(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """기존 User를 수정 후 save하면 변경사항이 영속화된다."""
    user = User.create(
        username="sync_original",
        email="sync_original@example.com",
        password_hash="original_hash",
    )

    with transaction:
        user_repository.save(user)
        user.username = "sync_updated"
        user.email = "sync_updated@example.com"
        user_repository.save(user)
        retrieved_user = user_repository.get(user.uid)

        assert retrieved_user.username == "sync_updated"
        assert retrieved_user.email == "sync_updated@example.com"
