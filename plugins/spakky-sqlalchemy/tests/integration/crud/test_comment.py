"""Comment entity CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IAsyncGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.apps.models.comment import Comment
from tests.apps.models.post import Post
from tests.apps.models.user import User


@pytest.fixture(name="comment_repository", scope="function")
def comment_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[Comment, UUID]:
    """Get Comment repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[Comment, UUID])


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[User, UUID]:
    """Get User repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[User, UUID])


@pytest.fixture(name="post_repository", scope="function")
def post_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[Post, UUID]:
    """Get Post repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[Post, UUID])


async def create_test_user(
    async_transaction: AsyncTransaction,
    user_repository: IAsyncGenericRepository[User, UUID],
) -> User:
    """테스트용 User를 생성하고 저장한다."""
    user = User.create(
        username=f"author_{uuid4().hex[:8]}",
        email=f"author_{uuid4().hex[:8]}@example.com",
        password_hash="hashed",
    )
    async with async_transaction:
        return await user_repository.save(user)


async def create_test_post(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    author_id: UUID,
) -> Post:
    """테스트용 Post를 생성하고 저장한다."""
    post = Post.create(
        author_id=author_id,
        title=f"Post_{uuid4().hex[:8]}",
        content="Test post content",
    )
    async with async_transaction:
        return await post_repository.save(post)


@pytest.mark.asyncio
async def test_comment_save_expect_persisted(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """새 Comment를 save하면 데이터베이스에 영속화된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Test comment content",
    )

    async with async_transaction:
        saved_comment = await comment_repository.save(comment)

        assert saved_comment.uid == comment.uid
        assert saved_comment.post_id == post.uid
        assert saved_comment.author_id == author.uid
        assert saved_comment.content == "Test comment content"


@pytest.mark.asyncio
async def test_comment_save_all_expect_all_persisted(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """여러 Comment를 save_all하면 모두 영속화된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comments = [
        Comment.create(
            post_id=post.uid,
            author_id=author.uid,
            content=f"Comment {i}",
        )
        for i in range(3)
    ]

    async with async_transaction:
        saved_comments = await comment_repository.save_all(comments)

        assert len(saved_comments) == 3
        for i, saved_comment in enumerate(saved_comments):
            assert saved_comment.uid == comments[i].uid


@pytest.mark.asyncio
async def test_comment_get_existing_expect_returned(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment를 get하면 해당 엔티티가 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Find this comment",
    )

    async with async_transaction:
        await comment_repository.save(comment)
        retrieved_comment = await comment_repository.get(comment.uid)

        assert retrieved_comment.uid == comment.uid
        assert retrieved_comment.content == "Find this comment"


@pytest.mark.asyncio
async def test_comment_get_nonexistent_expect_entity_not_found_error(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
) -> None:
    """존재하지 않는 Comment를 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        with pytest.raises(EntityNotFoundError) as exc_info:
            await comment_repository.get(nonexistent_id)

        assert exc_info.value.args[0] == nonexistent_id


@pytest.mark.asyncio
async def test_comment_get_or_none_existing_expect_returned(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment를 get_or_none하면 해당 엔티티가 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Nullable find",
    )

    async with async_transaction:
        await comment_repository.save(comment)
        retrieved_comment = await comment_repository.get_or_none(comment.uid)

        assert retrieved_comment is not None
        assert retrieved_comment.uid == comment.uid


@pytest.mark.asyncio
async def test_comment_get_or_none_nonexistent_expect_none(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
) -> None:
    """존재하지 않는 Comment를 get_or_none하면 None이 반환된다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        retrieved_comment = await comment_repository.get_or_none(nonexistent_id)

        assert retrieved_comment is None


@pytest.mark.asyncio
async def test_comment_contains_existing_expect_true(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment ID로 contains하면 True가 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Exists check",
    )

    async with async_transaction:
        await comment_repository.save(comment)
        exists = await comment_repository.contains(comment.uid)

        assert exists is True


@pytest.mark.asyncio
async def test_comment_contains_nonexistent_expect_false(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
) -> None:
    """존재하지 않는 Comment ID로 contains하면 False가 반환된다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        exists = await comment_repository.contains(nonexistent_id)

        assert exists is False


@pytest.mark.asyncio
async def test_comment_range_existing_expect_all_returned(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """여러 Comment ID로 range하면 해당 엔티티들이 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comments = [
        Comment.create(
            post_id=post.uid,
            author_id=author.uid,
            content=f"Range comment {i}",
        )
        for i in range(3)
    ]
    comment_ids = [comment.uid for comment in comments]

    async with async_transaction:
        await comment_repository.save_all(comments)
        retrieved_comments = await comment_repository.range(comment_ids)

        assert len(retrieved_comments) == 3
        retrieved_ids = {comment.uid for comment in retrieved_comments}
        assert retrieved_ids == set(comment_ids)


@pytest.mark.asyncio
async def test_comment_range_partial_existing_expect_only_existing_returned(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """일부만 존재하는 ID로 range하면 존재하는 것만 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Partial range",
    )
    nonexistent_id = uuid4()

    async with async_transaction:
        await comment_repository.save(comment)
        retrieved_comments = await comment_repository.range(
            [comment.uid, nonexistent_id]
        )

        assert len(retrieved_comments) == 1
        assert retrieved_comments[0].uid == comment.uid


@pytest.mark.asyncio
async def test_comment_range_empty_list_expect_empty_result(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
) -> None:
    """빈 ID 목록으로 range하면 빈 결과가 반환된다."""
    async with async_transaction:
        retrieved_comments = await comment_repository.range([])

        assert len(retrieved_comments) == 0


@pytest.mark.asyncio
async def test_comment_delete_existing_expect_removed(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하는 Comment를 delete하면 데이터베이스에서 제거된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="To delete",
    )

    async with async_transaction:
        await comment_repository.save(comment)
        deleted_comment = await comment_repository.delete(comment)

        assert deleted_comment.uid == comment.uid
        assert await comment_repository.contains(comment.uid) is False


@pytest.mark.asyncio
async def test_comment_delete_all_expect_all_removed(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """여러 Comment를 delete_all하면 모두 제거된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comments = [
        Comment.create(
            post_id=post.uid,
            author_id=author.uid,
            content=f"Delete all {i}",
        )
        for i in range(3)
    ]

    async with async_transaction:
        await comment_repository.save_all(comments)
        deleted_comments = await comment_repository.delete_all(comments)

        assert len(deleted_comments) == 3
        for comment in comments:
            assert await comment_repository.contains(comment.uid) is False


@pytest.mark.asyncio
async def test_comment_save_updated_expect_changes_persisted(
    async_transaction: AsyncTransaction,
    comment_repository: IAsyncGenericRepository[Comment, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """기존 Comment를 수정 후 save하면 변경사항이 영속화된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = await create_test_post(async_transaction, post_repository, author.uid)
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Original content",
    )

    async with async_transaction:
        await comment_repository.save(comment)
        comment.content = "Updated content"
        await comment_repository.save(comment)
        retrieved_comment = await comment_repository.get(comment.uid)

        assert retrieved_comment.content == "Updated content"
