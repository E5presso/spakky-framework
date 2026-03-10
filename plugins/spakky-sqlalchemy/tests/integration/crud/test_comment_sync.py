"""Comment entity sync CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import Transaction
from tests.apps.models.comment import Comment
from tests.apps.models.post import Post
from tests.apps.models.user import User


@pytest.fixture(name="comment_repository", scope="function")
def comment_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[Comment, UUID]:
    """Get sync Comment repository from application container."""
    return app.container.get(type_=IGenericRepository[Comment, UUID])


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[User, UUID]:
    """Get sync User repository from application container."""
    return app.container.get(type_=IGenericRepository[User, UUID])


@pytest.fixture(name="post_repository", scope="function")
def post_repository_fixture(
    app: SpakkyApplication,
) -> IGenericRepository[Post, UUID]:
    """Get sync Post repository from application container."""
    return app.container.get(type_=IGenericRepository[Post, UUID])


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


def create_test_post(
    transaction: Transaction,
    post_repository: IGenericRepository[Post, UUID],
    author_id: UUID,
) -> Post:
    """테스트용 Post를 생성하고 저장한다."""
    post = Post.create(
        author_id=author_id,
        title=f"Sync_Post_{uuid4().hex[:8]}",
        content="Sync test post content",
    )
    with transaction:
        return post_repository.save(post)


def test_comment_save_expect_persisted(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """새 Comment를 save하면 데이터베이스에 영속화된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync test comment content",
    )

    with transaction:
        saved_comment = comment_repository.save(comment)

        assert saved_comment.uid == comment.uid
        assert saved_comment.post_id == post.uid
        assert saved_comment.author_id == author.uid
        assert saved_comment.content == "Sync test comment content"


def test_comment_save_all_expect_all_persisted(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """여러 Comment를 save_all하면 모두 영속화된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comments = [
        Comment.create(
            post_id=post.uid,
            author_id=author.uid,
            content=f"Sync Comment {i}",
        )
        for i in range(3)
    ]

    with transaction:
        saved_comments = comment_repository.save_all(comments)

        assert len(saved_comments) == 3
        for i, saved_comment in enumerate(saved_comments):
            assert saved_comment.uid == comments[i].uid


def test_comment_get_existing_expect_returned(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment를 get하면 해당 엔티티가 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync find this comment",
    )

    with transaction:
        comment_repository.save(comment)
        retrieved_comment = comment_repository.get(comment.uid)

        assert retrieved_comment.uid == comment.uid
        assert retrieved_comment.content == "Sync find this comment"


def test_comment_get_nonexistent_expect_entity_not_found_error(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
) -> None:
    """존재하지 않는 Comment를 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_id = uuid4()

    with transaction:
        with pytest.raises(EntityNotFoundError) as exc_info:
            comment_repository.get(nonexistent_id)

        assert exc_info.value.args[0] == nonexistent_id


def test_comment_get_or_none_existing_expect_returned(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment를 get_or_none하면 해당 엔티티가 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync nullable find",
    )

    with transaction:
        comment_repository.save(comment)
        retrieved_comment = comment_repository.get_or_none(comment.uid)

        assert retrieved_comment is not None
        assert retrieved_comment.uid == comment.uid


def test_comment_get_or_none_nonexistent_expect_none(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
) -> None:
    """존재하지 않는 Comment를 get_or_none하면 None이 반환된다."""
    nonexistent_id = uuid4()

    with transaction:
        retrieved_comment = comment_repository.get_or_none(nonexistent_id)

        assert retrieved_comment is None


def test_comment_contains_existing_expect_true(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment ID로 contains하면 True가 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync exists check",
    )

    with transaction:
        comment_repository.save(comment)
        exists = comment_repository.contains(comment.uid)

        assert exists is True


def test_comment_contains_nonexistent_expect_false(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
) -> None:
    """존재하지 않는 Comment ID로 contains하면 False가 반환된다."""
    nonexistent_id = uuid4()

    with transaction:
        exists = comment_repository.contains(nonexistent_id)

        assert exists is False


def test_comment_range_existing_expect_all_returned(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """여러 Comment ID로 range하면 해당 엔티티들이 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comments = [
        Comment.create(
            post_id=post.uid,
            author_id=author.uid,
            content=f"Sync range comment {i}",
        )
        for i in range(3)
    ]
    comment_ids = [comment.uid for comment in comments]

    with transaction:
        comment_repository.save_all(comments)
        retrieved_comments = comment_repository.range(comment_ids)

        assert len(retrieved_comments) == 3
        retrieved_ids = {comment.uid for comment in retrieved_comments}
        assert retrieved_ids == set(comment_ids)


def test_comment_range_partial_existing_expect_only_existing_returned(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """일부만 존재하는 ID로 range하면 존재하는 것만 반환된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync partial range",
    )
    nonexistent_id = uuid4()

    with transaction:
        comment_repository.save(comment)
        retrieved_comments = comment_repository.range([comment.uid, nonexistent_id])

        assert len(retrieved_comments) == 1
        assert retrieved_comments[0].uid == comment.uid


def test_comment_range_empty_list_expect_empty_result(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
) -> None:
    """빈 ID 목록으로 range하면 빈 결과가 반환된다."""
    with transaction:
        retrieved_comments = comment_repository.range([])

        assert len(retrieved_comments) == 0


def test_comment_delete_existing_expect_removed(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment를 delete하면 데이터베이스에서 제거된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync to delete",
    )

    with transaction:
        comment_repository.save(comment)
        deleted_comment = comment_repository.delete(comment)

        assert deleted_comment.uid == comment.uid
        assert comment_repository.contains(comment.uid) is False


def test_comment_delete_all_expect_all_removed(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """여러 Comment를 delete_all하면 모두 제거된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comments = [
        Comment.create(
            post_id=post.uid,
            author_id=author.uid,
            content=f"Sync delete all {i}",
        )
        for i in range(3)
    ]

    with transaction:
        comment_repository.save_all(comments)
        deleted_comments = comment_repository.delete_all(comments)

        assert len(deleted_comments) == 3
        for comment in comments:
            assert comment_repository.contains(comment.uid) is False


def test_comment_save_updated_expect_changes_persisted(
    transaction: Transaction,
    comment_repository: IGenericRepository[Comment, UUID],
    user_repository: IGenericRepository[User, UUID],
    post_repository: IGenericRepository[Post, UUID],
) -> None:
    """기존 Comment를 수정 후 save하면 변경사항이 영속화된다."""
    author = create_test_user(transaction, user_repository)
    post = create_test_post(transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Sync original content",
    )

    with transaction:
        comment_repository.save(comment)
        comment.content = "Sync updated content"
        comment_repository.save(comment)
        retrieved_comment = comment_repository.get(comment.uid)

        assert retrieved_comment.content == "Sync updated content"
