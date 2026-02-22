"""Comment ORM table mapping for testing."""

from datetime import datetime
from typing import Self
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from tests.apps.models.comment import Comment


@Table(Comment)
class CommentTable(AbstractTable[Comment]):
    """ORM table mapping for Comment domain entity."""

    __tablename__ = "comments"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    post_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("posts.uid"),
        nullable=False,
    )
    author_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.uid"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)

    @classmethod
    def from_domain(cls, domain: Comment) -> Self:
        """Convert Comment domain entity to CommentTable ORM object.

        Args:
            domain: Comment domain entity.

        Returns:
            CommentTable ORM instance.
        """
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            post_id=domain.post_id,
            author_id=domain.author_id,
            content=domain.content,
        )

    def to_domain(self) -> Comment:
        """Convert CommentTable ORM object to Comment domain entity.

        Returns:
            Comment domain entity.
        """
        return Comment(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            post_id=self.post_id,
            author_id=self.author_id,
            content=self.content,
        )
