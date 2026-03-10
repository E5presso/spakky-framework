"""Comment domain model for testing."""

from typing import Self
from uuid import UUID

from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.aggregate_root import AbstractAggregateRoot


@mutable
class Comment(AbstractAggregateRoot[UUID]):
    """Comment domain entity for testing purposes."""

    post_id: UUID
    """ID of the post this comment belongs to."""

    author_id: UUID
    """ID of the user who wrote the comment."""

    content: str
    """Content of the comment."""

    @classmethod
    def next_id(cls) -> UUID:
        """Generate next unique identifier for Comment entity.

        Returns:
            New UUID7 identifier.
        """
        return uuid7()

    def validate(self) -> None:
        """Validate comment entity state.

        This is a test entity, so validation is minimal.
        """
        return

    @classmethod
    def create(
        cls,
        post_id: UUID,
        author_id: UUID,
        content: str,
    ) -> Self:
        """Factory method to create a new Comment.

        Args:
            post_id: ID of the parent post.
            author_id: ID of the comment author.
            content: Content of the comment.

        Returns:
            New Comment instance.
        """
        return cls(
            uid=cls.next_id(),
            post_id=post_id,
            author_id=author_id,
            content=content,
        )
