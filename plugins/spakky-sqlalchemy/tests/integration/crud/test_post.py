"""Post entity CRUD integration tests."""

from uuid import UUID, uuid4

import pytest
from spakky.core.application.application import SpakkyApplication
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IAsyncGenericRepository,
)

from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.apps.models.post import Post
from tests.apps.models.user import User


@pytest.fixture(name="post_repository", scope="function")
def post_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[Post, UUID]:
    """Get Post repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[Post, UUID])


@pytest.fixture(name="user_repository", scope="function")
def user_repository_fixture(
    app: SpakkyApplication,
) -> IAsyncGenericRepository[User, UUID]:
    """Get User repository from application container."""
    return app.container.get(type_=IAsyncGenericRepository[User, UUID])


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


@pytest.mark.asyncio
async def test_post_save_expect_persisted(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """새 Post를 save하면 데이터베이스에 영속화된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Test Title",
        content="Test content body",
    )

    async with async_transaction:
        saved_post = await post_repository.save(post)

        assert saved_post.uid == post.uid
        assert saved_post.author_id == author.uid
        assert saved_post.title == "Test Title"
        assert saved_post.content == "Test content body"


@pytest.mark.asyncio
async def test_post_save_all_expect_all_persisted(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """여러 Post를 save_all하면 모두 영속화된다."""
    author = await create_test_user(async_transaction, user_repository)
    posts = [
        Post.create(
            author_id=author.uid,
            title=f"Title {i}",
            content=f"Content {i}",
        )
        for i in range(3)
    ]

    async with async_transaction:
        saved_posts = await post_repository.save_all(posts)

        assert len(saved_posts) == 3
        for i, saved_post in enumerate(saved_posts):
            assert saved_post.uid == posts[i].uid


@pytest.mark.asyncio
async def test_post_get_existing_expect_returned(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 Post를 get하면 해당 엔티티가 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Find Me",
        content="Content to find",
    )

    async with async_transaction:
        await post_repository.save(post)
        retrieved_post = await post_repository.get(post.uid)

        assert retrieved_post.uid == post.uid
        assert retrieved_post.title == "Find Me"


@pytest.mark.asyncio
async def test_post_get_nonexistent_expect_entity_not_found_error(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하지 않는 Post를 get하면 EntityNotFoundError가 발생한다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        with pytest.raises(EntityNotFoundError) as exc_info:
            await post_repository.get(nonexistent_id)

        assert exc_info.value.args[0] == nonexistent_id


@pytest.mark.asyncio
async def test_post_get_or_none_existing_expect_returned(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 Post를 get_or_none하면 해당 엔티티가 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Nullable Find",
        content="Content",
    )

    async with async_transaction:
        await post_repository.save(post)
        retrieved_post = await post_repository.get_or_none(post.uid)

        assert retrieved_post is not None
        assert retrieved_post.uid == post.uid


@pytest.mark.asyncio
async def test_post_get_or_none_nonexistent_expect_none(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하지 않는 Post를 get_or_none하면 None이 반환된다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        retrieved_post = await post_repository.get_or_none(nonexistent_id)

        assert retrieved_post is None


@pytest.mark.asyncio
async def test_post_contains_existing_expect_true(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 Post ID로 contains하면 True가 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Exists Check",
        content="Content",
    )

    async with async_transaction:
        await post_repository.save(post)
        exists = await post_repository.contains(post.uid)

        assert exists is True


@pytest.mark.asyncio
async def test_post_contains_nonexistent_expect_false(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """존재하지 않는 Post ID로 contains하면 False가 반환된다."""
    nonexistent_id = uuid4()

    async with async_transaction:
        exists = await post_repository.contains(nonexistent_id)

        assert exists is False


@pytest.mark.asyncio
async def test_post_range_existing_expect_all_returned(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """여러 Post ID로 range하면 해당 엔티티들이 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    posts = [
        Post.create(
            author_id=author.uid,
            title=f"Range Post {i}",
            content=f"Content {i}",
        )
        for i in range(3)
    ]
    post_ids = [post.uid for post in posts]

    async with async_transaction:
        await post_repository.save_all(posts)
        retrieved_posts = await post_repository.range(post_ids)

        assert len(retrieved_posts) == 3
        retrieved_ids = {post.uid for post in retrieved_posts}
        assert retrieved_ids == set(post_ids)


@pytest.mark.asyncio
async def test_post_range_partial_existing_expect_only_existing_returned(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """일부만 존재하는 ID로 range하면 존재하는 것만 반환된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Partial Range",
        content="Content",
    )
    nonexistent_id = uuid4()

    async with async_transaction:
        await post_repository.save(post)
        retrieved_posts = await post_repository.range([post.uid, nonexistent_id])

        assert len(retrieved_posts) == 1
        assert retrieved_posts[0].uid == post.uid


@pytest.mark.asyncio
async def test_post_range_empty_list_expect_empty_result(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
) -> None:
    """빈 ID 목록으로 range하면 빈 결과가 반환된다."""
    async with async_transaction:
        retrieved_posts = await post_repository.range([])

        assert len(retrieved_posts) == 0


@pytest.mark.asyncio
async def test_post_delete_existing_expect_removed(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """존재하는 Post를 delete하면 데이터베이스에서 제거된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="To Delete",
        content="Content",
    )

    async with async_transaction:
        await post_repository.save(post)
        deleted_post = await post_repository.delete(post)

        assert deleted_post.uid == post.uid
        assert await post_repository.contains(post.uid) is False


@pytest.mark.asyncio
async def test_post_delete_all_expect_all_removed(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """여러 Post를 delete_all하면 모두 제거된다."""
    author = await create_test_user(async_transaction, user_repository)
    posts = [
        Post.create(
            author_id=author.uid,
            title=f"Delete All {i}",
            content=f"Content {i}",
        )
        for i in range(3)
    ]

    async with async_transaction:
        await post_repository.save_all(posts)
        deleted_posts = await post_repository.delete_all(posts)

        assert len(deleted_posts) == 3
        for post in posts:
            assert await post_repository.contains(post.uid) is False


@pytest.mark.asyncio
async def test_post_save_updated_expect_changes_persisted(
    async_transaction: AsyncTransaction,
    post_repository: IAsyncGenericRepository[Post, UUID],
    user_repository: IAsyncGenericRepository[User, UUID],
) -> None:
    """기존 Post를 수정 후 save하면 변경사항이 영속화된다."""
    author = await create_test_user(async_transaction, user_repository)
    post = Post.create(
        author_id=author.uid,
        title="Original Title",
        content="Original content",
    )

    async with async_transaction:
        await post_repository.save(post)
        post.title = "Updated Title"
        post.content = "Updated content"
        await post_repository.save(post)
        retrieved_post = await post_repository.get(post.uid)

        assert retrieved_post.title == "Updated Title"
        assert retrieved_post.content == "Updated content"
