"""Test entities for SQLAlchemy integration tests."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID, uuid4

from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import (
    ForeignKey,
    ReferentialAction,
)
from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
from spakky.plugins.sqlalchemy.orm.fields.datetime import DateTime
from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
from spakky.plugins.sqlalchemy.orm.fields.numeric import Integer
from spakky.plugins.sqlalchemy.orm.fields.string import String
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.table import Table


class UserStatus(Enum):
    """User status enum."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


@Table(table_name="users")
@dataclass
class User:
    """Test user entity."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    email: Annotated[str, String(length=255), Unique(name="uq_users_email")]
    username: Annotated[str, String(length=100), Index()]
    status: Annotated[UserStatus, EnumField(enum_class=UserStatus)]
    created_at: Annotated[datetime, DateTime(timezone=True)]

    def __post_init__(self) -> None:
        """Initialize entity."""


@Table(table_name="posts")
@dataclass
class Post:
    """Test post entity with foreign key."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    author_id: Annotated[
        UUID,
        Uuid(),
        ForeignKey(
            column="users.id",
            on_delete=ReferentialAction.CASCADE,
        ),
        Index(name="idx_posts_author_id"),
    ]
    title: Annotated[str, String(length=200)]
    content: Annotated[str, String(length=10000)]
    view_count: Annotated[int, Integer()]
    created_at: Annotated[datetime, DateTime(timezone=True)]

    def __post_init__(self) -> None:
        """Initialize entity."""


@Table(table_name="comments")
@dataclass
class Comment:
    """Test comment entity with multiple foreign keys."""

    id: Annotated[UUID, Uuid(), PrimaryKey()]
    post_id: Annotated[
        UUID,
        Uuid(),
        ForeignKey(column="posts.id", on_delete=ReferentialAction.CASCADE),
    ]
    author_id: Annotated[
        UUID,
        Uuid(),
        ForeignKey(column="users.id", on_delete=ReferentialAction.SET_NULL),
    ]
    content: Annotated[str, String(length=1000)]
    created_at: Annotated[datetime, DateTime(timezone=True)]

    def __post_init__(self) -> None:
        """Initialize entity."""


def create_user(
    user_id: UUID | None = None,
    email: str = "test@example.com",
    username: str = "testuser",
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    """Create a test user instance.

    Args:
        user_id: Optional user ID.
        email: User email.
        username: Username.
        status: User status.

    Returns:
        User instance.
    """
    return User(
        id=user_id or uuid4(),
        email=email,
        username=username,
        status=status,
        created_at=datetime.now(),
    )


def create_post(
    post_id: UUID | None = None,
    author_id: UUID | None = None,
    title: str = "Test Post",
    content: str = "Test content",
) -> Post:
    """Create a test post instance.

    Args:
        post_id: Optional post ID.
        author_id: Author user ID.
        title: Post title.
        content: Post content.

    Returns:
        Post instance.
    """
    return Post(
        id=post_id or uuid4(),
        author_id=author_id or uuid4(),
        title=title,
        content=content,
        view_count=0,
        created_at=datetime.now(),
    )


def create_comment(
    comment_id: UUID | None = None,
    post_id: UUID | None = None,
    author_id: UUID | None = None,
    content: str = "Test comment",
) -> Comment:
    """Create a test comment instance.

    Args:
        comment_id: Optional comment ID.
        post_id: Post ID.
        author_id: Author user ID.
        content: Comment content.

    Returns:
        Comment instance.
    """
    return Comment(
        id=comment_id or uuid4(),
        post_id=post_id or uuid4(),
        author_id=author_id or uuid4(),
        content=content,
        created_at=datetime.now(),
    )
