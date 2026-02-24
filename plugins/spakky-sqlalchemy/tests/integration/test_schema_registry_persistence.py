"""Integration tests for SchemaRegistry domain-to-ORM conversion and persistence."""

import pytest
from spakky.core.application.application import SpakkyApplication
from sqlalchemy import select

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from spakky.plugins.sqlalchemy.persistency.transaction import AsyncTransaction
from tests.apps.models import Comment, Post, User
from tests.apps.orm import CommentTable, PostTable, UserTable


@pytest.mark.asyncio
async def test_user_create_convert_save_and_query_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """User 도메인 모델의 생성, ORM 변환, 저장, 조회를 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    user = User.create(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password_123",
    )

    async with async_transaction:
        session = async_transaction.session
        user_table = schema_registry.from_domain(user)
        session.add(user_table)
        await session.flush()

        result = await session.execute(
            select(UserTable).where(UserTable.uid == user.uid)
        )
        queried_table = result.scalar_one()

        assert queried_table.uid == user.uid
        assert queried_table.username == user.username
        assert queried_table.email == user.email
        assert queried_table.password_hash == user.password_hash
        assert queried_table.version == user.version
        assert queried_table.created_at == user.created_at
        assert queried_table.updated_at == user.updated_at


@pytest.mark.asyncio
async def test_user_table_to_domain_conversion_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """조회된 UserTable을 User 도메인으로 변환하는 것을 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    user = User.create(
        username="domainuser",
        email="domain@example.com",
        password_hash="domain_hash_456",
    )

    async with async_transaction:
        session = async_transaction.session
        user_table = schema_registry.from_domain(user)
        session.add(user_table)
        await session.flush()

        result = await session.execute(
            select(UserTable).where(UserTable.uid == user.uid)
        )
        queried_table = result.scalar_one()
        restored_user = queried_table.to_domain()

        assert restored_user.uid == user.uid
        assert restored_user.username == user.username
        assert restored_user.email == user.email
        assert restored_user.password_hash == user.password_hash


@pytest.mark.asyncio
async def test_post_create_convert_save_and_query_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """Post 도메인 모델의 생성, ORM 변환, 저장, 조회를 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)

    author = User.create(
        username="author",
        email="author@example.com",
        password_hash="author_hash",
    )
    post = Post.create(
        author_id=author.uid,
        title="Test Post Title",
        content="This is the content of the test post.",
    )

    async with async_transaction:
        session = async_transaction.session
        session.add(schema_registry.from_domain(author))
        await session.flush()

        session.add(schema_registry.from_domain(post))
        await session.flush()

        result = await session.execute(
            select(PostTable).where(PostTable.uid == post.uid)
        )
        queried_table = result.scalar_one()

        assert queried_table.uid == post.uid
        assert queried_table.author_id == author.uid
        assert queried_table.title == post.title
        assert queried_table.content == post.content


@pytest.mark.asyncio
async def test_post_table_to_domain_conversion_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """조회된 PostTable을 Post 도메인으로 변환하는 것을 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)

    author = User.create(
        username="postauthor",
        email="postauthor@example.com",
        password_hash="post_author_hash",
    )
    post = Post.create(
        author_id=author.uid,
        title="Domain Post",
        content="Domain post content.",
    )

    async with async_transaction:
        session = async_transaction.session
        session.add(schema_registry.from_domain(author))
        await session.flush()

        session.add(schema_registry.from_domain(post))
        await session.flush()

        result = await session.execute(
            select(PostTable).where(PostTable.uid == post.uid)
        )
        queried_table = result.scalar_one()
        restored_post = queried_table.to_domain()

        assert restored_post.uid == post.uid
        assert restored_post.author_id == post.author_id
        assert restored_post.title == post.title
        assert restored_post.content == post.content


@pytest.mark.asyncio
async def test_comment_create_convert_save_and_query_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """Comment 도메인 모델의 생성, ORM 변환, 저장, 조회를 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)

    author = User.create(
        username="commentauthor",
        email="commentauthor@example.com",
        password_hash="comment_author_hash",
    )
    post = Post.create(
        author_id=author.uid,
        title="Comment Test Post",
        content="Post for comment testing.",
    )
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="This is a test comment.",
    )

    async with async_transaction:
        session = async_transaction.session
        session.add(schema_registry.from_domain(author))
        await session.flush()

        session.add(schema_registry.from_domain(post))
        await session.flush()

        session.add(schema_registry.from_domain(comment))
        await session.flush()

        result = await session.execute(
            select(CommentTable).where(CommentTable.uid == comment.uid)
        )
        queried_table = result.scalar_one()

        assert queried_table.uid == comment.uid
        assert queried_table.post_id == post.uid
        assert queried_table.author_id == author.uid
        assert queried_table.content == comment.content


@pytest.mark.asyncio
async def test_comment_table_to_domain_conversion_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """조회된 CommentTable을 Comment 도메인으로 변환하는 것을 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)

    author = User.create(
        username="domaincommentauthor",
        email="domaincommentauthor@example.com",
        password_hash="domain_comment_hash",
    )
    post = Post.create(
        author_id=author.uid,
        title="Domain Comment Post",
        content="Post for domain comment testing.",
    )
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Domain comment content.",
    )

    async with async_transaction:
        session = async_transaction.session
        session.add(schema_registry.from_domain(author))
        await session.flush()

        session.add(schema_registry.from_domain(post))
        await session.flush()

        session.add(schema_registry.from_domain(comment))
        await session.flush()

        result = await session.execute(
            select(CommentTable).where(CommentTable.uid == comment.uid)
        )
        queried_table = result.scalar_one()
        restored_comment = queried_table.to_domain()

        assert restored_comment.uid == comment.uid
        assert restored_comment.post_id == comment.post_id
        assert restored_comment.author_id == comment.author_id
        assert restored_comment.content == comment.content


@pytest.mark.asyncio
async def test_multiple_entities_relationship_query_expect_success(
    app: SpakkyApplication,
    async_transaction: AsyncTransaction,
) -> None:
    """User, Post, Comment 간의 관계 조회를 검증한다."""
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)

    author = User.create(
        username="relauthor",
        email="relauthor@example.com",
        password_hash="rel_author_hash",
    )
    post1 = Post.create(
        author_id=author.uid,
        title="First Post",
        content="First post content.",
    )
    post2 = Post.create(
        author_id=author.uid,
        title="Second Post",
        content="Second post content.",
    )
    comment1 = Comment.create(
        post_id=post1.uid,
        author_id=author.uid,
        content="Comment on first post.",
    )
    comment2 = Comment.create(
        post_id=post1.uid,
        author_id=author.uid,
        content="Another comment on first post.",
    )

    async with async_transaction:
        session = async_transaction.session
        session.add(schema_registry.from_domain(author))
        await session.flush()

        session.add(schema_registry.from_domain(post1))
        session.add(schema_registry.from_domain(post2))
        await session.flush()

        session.add(schema_registry.from_domain(comment1))
        session.add(schema_registry.from_domain(comment2))
        await session.flush()

        posts_result = await session.execute(
            select(PostTable).where(PostTable.author_id == author.uid)
        )
        posts = posts_result.scalars().all()

        comments_result = await session.execute(
            select(CommentTable).where(CommentTable.post_id == post1.uid)
        )
        comments = comments_result.scalars().all()

        assert len(posts) == 2
        assert {p.title for p in posts} == {"First Post", "Second Post"}
        assert len(comments) == 2
        assert {c.content for c in comments} == {
            "Comment on first post.",
            "Another comment on first post.",
        }
