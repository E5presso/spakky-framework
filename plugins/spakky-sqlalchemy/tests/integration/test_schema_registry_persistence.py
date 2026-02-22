"""Integration tests for SchemaRegistry domain-to-ORM conversion and persistence."""

import pytest
from spakky.core.application.application import SpakkyApplication
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spakky.plugins.sqlalchemy.orm.schema_registry import SchemaRegistry
from tests.apps.models import Comment, Post, User
from tests.apps.orm import CommentTable, PostTable, UserTable


@pytest.mark.asyncio
async def test_user_create_convert_save_and_query_expect_success(
    app: SpakkyApplication,
    session: AsyncSession,
) -> None:
    """Test User domain model creation, ORM conversion, save, and query."""
    # Arrange
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    user = User.create(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password_123",
    )

    # Act - Convert domain to ORM and save
    user_table = schema_registry.from_domain(user)
    session.add(user_table)
    await session.commit()

    # Assert - Query and verify
    result = await session.execute(select(UserTable).where(UserTable.uid == user.uid))
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
    session: AsyncSession,
) -> None:
    """Test converting queried UserTable back to User domain."""
    # Arrange
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    user = User.create(
        username="domainuser",
        email="domain@example.com",
        password_hash="domain_hash_456",
    )
    user_table = schema_registry.from_domain(user)
    session.add(user_table)
    await session.commit()

    # Act - Query and convert back to domain
    result = await session.execute(select(UserTable).where(UserTable.uid == user.uid))
    queried_table = result.scalar_one()
    restored_user = queried_table.to_domain()

    # Assert
    assert restored_user.uid == user.uid
    assert restored_user.username == user.username
    assert restored_user.email == user.email
    assert restored_user.password_hash == user.password_hash


@pytest.mark.asyncio
async def test_post_create_convert_save_and_query_expect_success(
    app: SpakkyApplication,
    session: AsyncSession,
) -> None:
    """Test Post domain model creation, ORM conversion, save, and query."""
    # Arrange - Create author first
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    author = User.create(
        username="author",
        email="author@example.com",
        password_hash="author_hash",
    )
    author_table = schema_registry.from_domain(author)
    session.add(author_table)
    await session.commit()

    # Act - Create and save post
    post = Post.create(
        author_id=author.uid,
        title="Test Post Title",
        content="This is the content of the test post.",
    )
    post_table = schema_registry.from_domain(post)
    session.add(post_table)
    await session.commit()

    # Assert - Query and verify
    result = await session.execute(select(PostTable).where(PostTable.uid == post.uid))
    queried_table = result.scalar_one()

    assert queried_table.uid == post.uid
    assert queried_table.author_id == author.uid
    assert queried_table.title == post.title
    assert queried_table.content == post.content


@pytest.mark.asyncio
async def test_post_table_to_domain_conversion_expect_success(
    app: SpakkyApplication,
    session: AsyncSession,
) -> None:
    """Test converting queried PostTable back to Post domain."""
    # Arrange - Create author and post
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    author = User.create(
        username="postauthor",
        email="postauthor@example.com",
        password_hash="post_author_hash",
    )
    session.add(schema_registry.from_domain(author))
    await session.commit()

    post = Post.create(
        author_id=author.uid,
        title="Domain Post",
        content="Domain post content.",
    )
    session.add(schema_registry.from_domain(post))
    await session.commit()

    # Act - Query and convert back to domain
    result = await session.execute(select(PostTable).where(PostTable.uid == post.uid))
    queried_table = result.scalar_one()
    restored_post = queried_table.to_domain()

    # Assert
    assert restored_post.uid == post.uid
    assert restored_post.author_id == post.author_id
    assert restored_post.title == post.title
    assert restored_post.content == post.content


@pytest.mark.asyncio
async def test_comment_create_convert_save_and_query_expect_success(
    app: SpakkyApplication,
    session: AsyncSession,
) -> None:
    """Test Comment domain model creation, ORM conversion, save, and query."""
    # Arrange - Create author and post first
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    author = User.create(
        username="commentauthor",
        email="commentauthor@example.com",
        password_hash="comment_author_hash",
    )
    session.add(schema_registry.from_domain(author))
    await session.commit()

    post = Post.create(
        author_id=author.uid,
        title="Comment Test Post",
        content="Post for comment testing.",
    )
    session.add(schema_registry.from_domain(post))
    await session.commit()

    # Act - Create and save comment
    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="This is a test comment.",
    )
    comment_table = schema_registry.from_domain(comment)
    session.add(comment_table)
    await session.commit()

    # Assert - Query and verify
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
    session: AsyncSession,
) -> None:
    """Test converting queried CommentTable back to Comment domain."""
    # Arrange - Create author, post, and comment
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    author = User.create(
        username="domaincommentauthor",
        email="domaincommentauthor@example.com",
        password_hash="domain_comment_hash",
    )
    session.add(schema_registry.from_domain(author))
    await session.commit()

    post = Post.create(
        author_id=author.uid,
        title="Domain Comment Post",
        content="Post for domain comment testing.",
    )
    session.add(schema_registry.from_domain(post))
    await session.commit()

    comment = Comment.create(
        post_id=post.uid,
        author_id=author.uid,
        content="Domain comment content.",
    )
    session.add(schema_registry.from_domain(comment))
    await session.commit()

    # Act - Query and convert back to domain
    result = await session.execute(
        select(CommentTable).where(CommentTable.uid == comment.uid)
    )
    queried_table = result.scalar_one()
    restored_comment = queried_table.to_domain()

    # Assert
    assert restored_comment.uid == comment.uid
    assert restored_comment.post_id == comment.post_id
    assert restored_comment.author_id == comment.author_id
    assert restored_comment.content == comment.content


@pytest.mark.asyncio
async def test_multiple_entities_relationship_query_expect_success(
    app: SpakkyApplication,
    session: AsyncSession,
) -> None:
    """Test querying related entities across User, Post, and Comment."""
    # Arrange - Create full hierarchy
    schema_registry: SchemaRegistry = app.container.get(type_=SchemaRegistry)
    author = User.create(
        username="relauthor",
        email="relauthor@example.com",
        password_hash="rel_author_hash",
    )
    session.add(schema_registry.from_domain(author))
    await session.commit()

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
    session.add(schema_registry.from_domain(post1))
    session.add(schema_registry.from_domain(post2))
    await session.commit()

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
    session.add(schema_registry.from_domain(comment1))
    session.add(schema_registry.from_domain(comment2))
    await session.commit()

    # Act - Query posts by author
    posts_result = await session.execute(
        select(PostTable).where(PostTable.author_id == author.uid)
    )
    posts = posts_result.scalars().all()

    # Act - Query comments by post
    comments_result = await session.execute(
        select(CommentTable).where(CommentTable.post_id == post1.uid)
    )
    comments = comments_result.scalars().all()

    # Assert
    assert len(posts) == 2
    assert {p.title for p in posts} == {"First Post", "Second Post"}
    assert len(comments) == 2
    assert {c.content for c in comments} == {
        "Comment on first post.",
        "Another comment on first post.",
    }
