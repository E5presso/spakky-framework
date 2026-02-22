"""Post ORM table mapping for testing."""

from datetime import datetime
from typing import Self
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractTable, Table
from tests.apps.models.post import Post


@Table(Post)
class PostTable(AbstractTable[Post]):
    """ORM table mapping for Post domain entity."""

    __tablename__ = "posts"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    author_id: Mapped[UUID] = mapped_column(
        Uuid(),
        ForeignKey("users.uid"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)

    @classmethod
    def from_domain(cls, domain: Post) -> Self:
        """Convert Post domain entity to PostTable ORM object.

        Args:
            domain: Post domain entity.

        Returns:
            PostTable ORM instance.
        """
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            author_id=domain.author_id,
            title=domain.title,
            content=domain.content,
        )

    def to_domain(self) -> Post:
        """Convert PostTable ORM object to Post domain entity.

        Returns:
            Post domain entity.
        """
        return Post(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            author_id=self.author_id,
            title=self.title,
            content=self.content,
        )
