"""Test entities with relationship annotations for integration tests."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import (
    ForeignKey,
    ReferentialAction,
)
from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.entity_ref import EntityRef
from spakky.plugins.sqlalchemy.orm.fields.datetime import DateTime
from spakky.plugins.sqlalchemy.orm.fields.string import String
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.relationships.cascade import CascadeOption
from spakky.plugins.sqlalchemy.orm.relationships.many_to_one import ManyToOne
from spakky.plugins.sqlalchemy.orm.relationships.one_to_many import OneToMany
from spakky.plugins.sqlalchemy.orm.relationships.one_to_one import OneToOne
from spakky.plugins.sqlalchemy.orm.table import Table


@Table(table_name="authors")
@dataclass
class Author:
    """Author entity with OneToMany and OneToOne relationships."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    name: Annotated[str, String(length=100)]
    created_at: Annotated[datetime, DateTime(timezone=True)]

    # OneToMany relationship to Article - forward ref, use string-based EntityRef
    articles: Annotated[
        "list[Article]",
        OneToMany(
            back_populates=EntityRef("Article", "author"),
            cascade=CascadeOption.ALL_DELETE_ORPHAN,
            order_by=EntityRef("Article", "title"),
        ),
    ] = field(default_factory=list)

    # OneToOne relationship to Profile - forward ref, use string-based EntityRef
    profile: Annotated[
        "Profile | None",
        OneToOne(back_populates=EntityRef("Profile", "author")),
    ] = field(default=None)

    def __post_init__(self) -> None:
        """Initialize entity."""


@Table(table_name="articles")
@dataclass
class Article:
    """Article entity with ManyToOne relationship."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    author_id: Annotated[
        UUID,
        Uuid(),
        ForeignKey(
            column=EntityRef(Author, lambda t: t.id),
            on_delete=ReferentialAction.CASCADE,
        ),
    ]
    title: Annotated[str, String(length=200)]
    content: Annotated[str, String(length=10000)]
    created_at: Annotated[datetime, DateTime(timezone=True)]

    # ManyToOne relationship to Author - Author is defined, use lambda accessor
    author: Annotated[
        Author | None,
        ManyToOne(back_populates=EntityRef(Author, lambda t: t.articles)),
    ] = field(default=None)

    def __post_init__(self) -> None:
        """Initialize entity."""


@Table(table_name="profiles")
@dataclass
class Profile:
    """Profile entity with OneToOne back-reference."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    author_id: Annotated[
        UUID,
        Uuid(),
        ForeignKey(
            column=EntityRef(Author, lambda t: t.id),
            on_delete=ReferentialAction.CASCADE,
        ),
    ]
    bio: Annotated[str, String(length=1000)]
    website: Annotated[str | None, String(length=255)] = field(default=None)

    # OneToOne back-reference to Author - Author is defined, use lambda accessor
    author: Annotated[
        Author | None,
        OneToOne(back_populates=EntityRef(Author, lambda t: t.profile)),
    ] = field(default=None)

    def __post_init__(self) -> None:
        """Initialize entity."""


def create_author(
    author_id: UUID | None = None,
    name: str = "Test Author",
) -> Author:
    """Create a test author instance.

    Args:
        author_id: Optional author ID.
        name: Author name.

    Returns:
        Author instance.
    """
    return Author(
        id=author_id or uuid4(),
        name=name,
        created_at=datetime.now(),
    )


def create_article(
    article_id: UUID | None = None,
    author_id: UUID | None = None,
    title: str = "Test Article",
    content: str = "Test content",
) -> Article:
    """Create a test article instance.

    Args:
        article_id: Optional article ID.
        author_id: Author ID.
        title: Article title.
        content: Article content.

    Returns:
        Article instance.
    """
    return Article(
        id=article_id or uuid4(),
        author_id=author_id or uuid4(),
        title=title,
        content=content,
        created_at=datetime.now(),
    )


def create_profile(
    profile_id: UUID | None = None,
    author_id: UUID | None = None,
    bio: str = "Test bio",
    website: str | None = None,
) -> Profile:
    """Create a test profile instance.

    Args:
        profile_id: Optional profile ID.
        author_id: Author ID.
        bio: Profile bio.
        website: Optional website URL.

    Returns:
        Profile instance.
    """
    return Profile(
        id=profile_id or uuid4(),
        author_id=author_id or uuid4(),
        bio=bio,
        website=website,
    )
