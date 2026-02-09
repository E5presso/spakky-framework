"""Integration tests for SQLAlchemy ORM relationships."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from spakky.plugins.sqlalchemy.orm.extractor import Extractor, RelationInfo
from spakky.plugins.sqlalchemy.orm.registry import ModelRegistry
from spakky.plugins.sqlalchemy.orm.relationships.base import RelationType
from spakky.plugins.sqlalchemy.orm.relationships.cascade import CascadeOption
from spakky.plugins.sqlalchemy.orm.relationships.many_to_one import ManyToOne
from spakky.plugins.sqlalchemy.orm.relationships.one_to_many import OneToMany
from spakky.plugins.sqlalchemy.orm.relationships.one_to_one import OneToOne
from tests.apps.entities import Post, create_post, create_user
from tests.apps.entities_with_relations import Article, Author, Profile

# =============================================================================
# Foreign Key Relationship Tests
# =============================================================================


@pytest.mark.asyncio
async def test_session_add_post_with_author_expect_fk_set(
    session: AsyncSession,
) -> None:
    """Post 엔티티 생성 시 author_id FK가 올바르게 설정되는지 검증한다."""
    user = create_user(email="author@example.com")
    session.add(user)
    await session.commit()

    post = create_post(
        author_id=user.id,
        title="My First Post",
        content="Hello World!",
    )
    session.add(post)
    await session.commit()

    saved_post = await session.get(Post, post.id)

    assert saved_post is not None
    assert saved_post.author_id == user.id
    assert saved_post.title == "My First Post"


@pytest.mark.asyncio
async def test_session_delete_user_expect_posts_cascade_deleted(
    session: AsyncSession,
) -> None:
    """User 삭제 시 ON DELETE CASCADE로 관련 Post가 삭제되는지 검증한다."""
    user = create_user(email="cascade@example.com")
    session.add(user)
    await session.commit()

    post = create_post(author_id=user.id, title="Will be deleted")
    session.add(post)
    await session.commit()

    post_id = post.id

    await session.delete(user)
    await session.commit()

    # Expire all cached objects to force DB reload
    session.expire_all()

    deleted_post = await session.get(Post, post_id)

    assert deleted_post is None


@pytest.mark.asyncio
async def test_session_add_multiple_posts_expect_all_saved(
    session: AsyncSession,
) -> None:
    """한 User에 여러 Post를 추가할 수 있는지 검증한다."""
    user = create_user(email="multi@example.com")
    session.add(user)
    await session.commit()

    posts = [create_post(author_id=user.id, title=f"Post {i}") for i in range(3)]
    session.add_all(posts)
    await session.commit()

    result = await session.execute(
        text("SELECT COUNT(*) FROM posts WHERE author_id = :author_id"),
        {"author_id": str(user.id)},
    )
    count = result.scalar_one()

    assert count == 3


# =============================================================================
# Relationship Extraction Tests
# =============================================================================


def test_extractor_extracts_one_to_many_relation_expect_relation_info(
    registry: ModelRegistry,
) -> None:
    """Extractor가 OneToMany 관계를 올바르게 추출하는지 검증한다."""
    extractor = Extractor()
    model_info = extractor.extract(Author)

    # articles 필드가 relations에 포함되어야 함
    articles_relation: RelationInfo[type[Article]] | None = next(
        (r for r in model_info.relations if r.name == "articles"), None
    )

    assert articles_relation is not None
    assert (
        articles_relation.relationship_metadata.relation_type
        == RelationType.ONE_TO_MANY
    )
    assert isinstance(articles_relation.relationship_metadata, OneToMany)
    assert (
        articles_relation.relationship_metadata.cascade
        == CascadeOption.ALL_DELETE_ORPHAN
    )
    assert articles_relation.relationship_metadata.order_by.name == "title"  # type: ignore[union-attr]
    # EntityRef with forward ref: back_populates_entity="Article" (string), back_populates_field="author"
    assert articles_relation.back_populates_entity == "Article"
    assert articles_relation.back_populates_field == "author"
    assert articles_relation.target_entity is Article
    assert articles_relation.collection_class is list


def test_extractor_extracts_many_to_one_relation_expect_relation_info(
    registry: ModelRegistry,
) -> None:
    """Extractor가 ManyToOne 관계를 올바르게 추출하는지 검증한다."""
    extractor = Extractor()
    model_info = extractor.extract(Article)

    # author 필드가 relations에 포함되어야 함
    author_relation: RelationInfo[type[Author]] | None = next(
        (r for r in model_info.relations if r.name == "author"), None
    )

    assert author_relation is not None
    assert (
        author_relation.relationship_metadata.relation_type == RelationType.MANY_TO_ONE
    )
    assert isinstance(author_relation.relationship_metadata, ManyToOne)
    # FieldRef(Author, "articles"): back_populates_entity=Author, back_populates_field="articles"
    assert author_relation.back_populates_entity is Author
    assert author_relation.back_populates_field == "articles"
    assert author_relation.target_entity is Author
    assert author_relation.collection_class is None  # ManyToOne은 컬렉션이 아님


def test_extractor_extracts_one_to_one_relation_expect_relation_info(
    registry: ModelRegistry,
) -> None:
    """Extractor가 OneToOne 관계를 올바르게 추출하는지 검증한다."""
    extractor = Extractor()
    model_info = extractor.extract(Author)

    # profile 필드가 relations에 포함되어야 함
    profile_relation: RelationInfo[type[Profile]] | None = next(
        (r for r in model_info.relations if r.name == "profile"), None
    )

    assert profile_relation is not None
    assert (
        profile_relation.relationship_metadata.relation_type == RelationType.ONE_TO_ONE
    )
    assert isinstance(profile_relation.relationship_metadata, OneToOne)
    # EntityRef with forward ref: back_populates_entity="Profile" (string), back_populates_field="author"
    assert profile_relation.back_populates_entity == "Profile"
    assert profile_relation.back_populates_field == "author"
    assert profile_relation.target_entity is Profile
    assert profile_relation.collection_class is None  # OneToOne은 컬렉션이 아님


def test_extractor_extracts_bidirectional_one_to_one_expect_both_sides(
    registry: ModelRegistry,
) -> None:
    """Extractor가 양방향 OneToOne 관계를 양쪽에서 추출하는지 검증한다."""
    extractor = Extractor()

    # Author 쪽
    author_info = extractor.extract(Author)
    author_profile_relation = next(
        (r for r in author_info.relations if r.name == "profile"), None
    )
    assert author_profile_relation is not None
    assert author_profile_relation.target_entity is Profile

    # Profile 쪽
    profile_info = extractor.extract(Profile)
    profile_author_relation = next(
        (r for r in profile_info.relations if r.name == "author"), None
    )
    assert profile_author_relation is not None
    assert (
        profile_author_relation.relationship_metadata.relation_type
        == RelationType.ONE_TO_ONE
    )
    assert profile_author_relation.target_entity is Author


def test_relation_field_excluded_from_columns_expect_not_in_columns(
    registry: ModelRegistry,
) -> None:
    """Relationship 필드는 columns에 포함되지 않아야 한다."""
    extractor = Extractor()
    model_info = extractor.extract(Author)

    # articles, profile은 columns에 없어야 함
    assert "articles" not in model_info.columns
    assert "profile" not in model_info.columns

    # 실제 컬럼은 있어야 함
    assert "id" in model_info.columns
    assert "name" in model_info.columns
    assert "created_at" in model_info.columns


def test_registry_registers_entities_with_relations_expect_tables_created(
    registry: ModelRegistry,
) -> None:
    """Relationship이 있는 엔티티가 테이블로 등록되는지 검증한다."""
    # 엔티티들이 등록되어 있어야 함
    assert Author in registry.registered_entities
    assert Article in registry.registered_entities
    assert Profile in registry.registered_entities

    # 테이블 이름 확인
    authors_table = registry.registered_entities[Author]
    articles_table = registry.registered_entities[Article]
    profiles_table = registry.registered_entities[Profile]

    assert authors_table.name == "authors"
    assert articles_table.name == "articles"
    assert profiles_table.name == "profiles"


@pytest.mark.asyncio
async def test_foreign_key_constraint_in_relation_entities_expect_fk_exists(
    session: AsyncSession,
) -> None:
    """Relationship 엔티티의 ForeignKey 제약조건이 DB에 존재하는지 검증한다."""
    # articles 테이블의 author_id FK 확인
    result = await session.execute(
        text(
            """
            SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_name = 'articles'
              AND tc.constraint_type = 'FOREIGN KEY'
            """
        )
    )
    fk_info = result.fetchall()

    # author_id -> authors.id FK가 존재해야 함
    author_fk = [row for row in fk_info if row[1] == "author_id"]
    assert len(author_fk) == 1
    assert author_fk[0][2] == "authors"
