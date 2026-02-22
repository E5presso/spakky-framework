"""Post domain model for testing."""

from typing import Self
from uuid import UUID

from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.entity import AbstractEntity


@mutable
class Post(AbstractEntity[UUID]):
    """Post domain entity for testing purposes."""

    author_id: UUID
    """ID of the user who authored the post."""

    title: str
    """Title of the post."""

    content: str
    """Main content of the post."""

    @classmethod
    def next_id(cls) -> UUID:
        """Generate next unique identifier for Post entity.

        Returns:
            New UUID7 identifier.
        """
        return uuid7()

    def validate(self) -> None:
        """Validate post entity state.

        This is a test entity, so validation is minimal.
        """
        return

    @classmethod
    def create(
        cls,
        author_id: UUID,
        title: str,
        content: str,
    ) -> Self:
        """Factory method to create a new Post.

        Args:
            author_id: ID of the post author.
            title: Title of the post.
            content: Main content of the post.

        Returns:
            New Post instance.
        """
        return cls(
            uid=cls.next_id(),
            author_id=author_id,
            title=title,
            content=content,
        )
