"""Post entity sync CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import Transaction
from tests.apps.models.post import Post
from tests.apps.models.user import User


@pytest.fixture(name="post_repository", scope="function")
def post_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[Post, UUID]:
    """Get sync Post repository from application container."""
    return app.container.get(type_=IGenericRepository[Post, UUID])


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[User, UUID]:
    """Get sync User repository from application container."""
    return app.container.get(type_=IGenericRepository[User, UUID])


def create_test_user(
    transaction: Transaction,
    user_repository: IGenericRepository[User, UUID],
) -> User:
    """테스트용 User를 생성하고 저장한다."""
    user = User.create(
        username=f"sync_author_{uuid4().hex[:8]}",
        email=f"sync_author_{uuid4().hex[:8]}@example.com",
        password_hash="hashed",
    )
    with transaction:
        return user_repository.save(user)


def test_post_save_expect_persisted(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """새 Post를 save하면 데이터베이스에 영속화된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync Test Title",
        content="Sync test content body",
    )

    with transaction:
        saved_post = post_repository.save(post)

        assert saved_post.uid == post.uid
        assert saved_post.author_id == author.uid
        assert saved_post.title == "Sync Test Title"
        assert saved_post.content == "Sync test content body"


def test_post_save_all_expect_all_persisted(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """여러 Post를 save_all하면 모두 영속화된다."""
    author = create_test_user(transaction, user_repository)
    posts = [
        Post.create(
            author_id=author.uid,
            title=f"Sync Title {i}",
            content=f"Sync Content {i}",
        )
        for i in range(3)
    ]

    with transaction:
        saved_posts = post_repository.save_all(posts)

        assert len(saved_posts) == 3
        for i, saved_post in enumerate(saved_posts):
            assert saved_post.uid == posts[i].uid


def test_post_get_existing_expect_returned(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 Post를 get하면 해당 엔티티가 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync Find Me",
        content="Sync content to find",
    )

    with transaction:
        post_repository.save(post)
        retrieved_post = post_repository.get(post.uid)

        assert retrieved_post.uid == post.uid
        assert retrieved_post.title == "Sync Find Me"


def test_post_get_nonexistent_expect_entity_not_found_error(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하지 않는 Post를 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_id = uuid4()

    with transaction:
        with pytest.raises(EntityNotFoundError) as exc_info:
            post_repository.get(nonexistent_id)

        assert exc_info.value.args[0] == nonexistent_id


def test_post_get_or_none_existing_expect_returned(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 Post를 get_or_none하면 해당 엔티티가 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync Nullable Find",
        content="Sync Content",
    )

    with transaction:
        post_repository.save(post)
        retrieved_post = post_repository.get_or_none(post.uid)

        assert retrieved_post is not None
        assert retrieved_post.uid == post.uid


def test_post_get_or_none_nonexistent_expect_none(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하지 않는 Post를 get_or_none하면 None이 반환된다."""
    nonexistent_id = uuid4()

    with transaction:
        retrieved_post = post_repository.get_or_none(nonexistent_id)

        assert retrieved_post is None


def test_post_contains_existing_expect_true(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 Post ID로 contains하면 True가 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync Exists Check",
        content="Sync Content",
    )

    with transaction:
        post_repository.save(post)
        exists = post_repository.contains(post.uid)

        assert exists is True


def test_post_contains_nonexistent_expect_false(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하지 않는 Post ID로 contains하면 False가 반환된다."""
    nonexistent_id = uuid4()

    with transaction:
        exists = post_repository.contains(nonexistent_id)

        assert exists is False


def test_post_range_existing_expect_all_returned(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """여러 Post ID로 range하면 해당 엔티티들이 반환된다."""
    author = create_test_user(transaction, user_repository)
    posts = [
        Post.create(
            author_id=author.uid,
            title=f"Sync Range Post {i}",
            content=f"Sync Content {i}",
        )
        for i in range(3)
    ]
    post_ids = [post.uid for post in posts]

    with transaction:
        post_repository.save_all(posts)
        retrieved_posts = post_repository.range(post_ids)

        assert len(retrieved_posts) == 3
        retrieved_ids = {post.uid for post in retrieved_posts}
        assert retrieved_ids == set(post_ids)


def test_post_range_partial_existing_expect_only_existing_returned(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """일부만 존재하는 ID로 range하면 존재하는 것만 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync Partial Range",
        content="Sync Content",
    )
    nonexistent_id = uuid4()

    with transaction:
        post_repository.save(post)
        retrieved_posts = post_repository.range([post.uid, nonexistent_id])

        assert len(retrieved_posts) == 1
        assert retrieved_posts[0].uid == post.uid


def test_post_range_empty_list_expect_empty_result(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """빈 ID 목록으로 range하면 빈 결과가 반환된다."""
    with transaction:
        retrieved_posts = post_repository.range([])

        assert len(retrieved_posts) == 0


def test_post_delete_existing_expect_removed(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """존재하는 Post를 delete하면 데이터베이스에서 제거된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync To Delete",
        content="Sync Content",
    )

    with transaction:
        post_repository.save(post)
        deleted_post = post_repository.delete(post)

        assert deleted_post.uid == post.uid
        assert post_repository.contains(post.uid) is False


def test_post_delete_all_expect_all_removed(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """여러 Post를 delete_all하면 모두 제거된다."""
    author = create_test_user(transaction, user_repository)
    posts = [
        Post.create(
            author_id=author.uid,
            title=f"Sync Delete All {i}",
            content=f"Sync Content {i}",
        )
        for i in range(3)
    ]

    with transaction:
        post_repository.save_all(posts)
        deleted_posts = post_repository.delete_all(posts)

        assert len(deleted_posts) == 3
        for post in posts:
            assert post_repository.contains(post.uid) is False


def test_post_save_updated_expect_changes_persisted(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    user_repository: IGenericRepository[User, UUID],
) -> None:
    """기존 Post를 수정 후 save하면 변경사항이 영속화된다."""
    author = create_test_user(transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Sync Original Title",
        content="Sync Original content",
    )

    with transaction:
        post_repository.save(post)
        post.title = "Sync Updated Title"
        post.content = "Sync Updated content"
        post_repository.save(post)
        retrieved_post = post_repository.get(post.uid)

        assert retrieved_post.title == "Sync Updated Title"
        assert retrieved_post.content == "Sync Updated content"
