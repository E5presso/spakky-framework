"""User ORM table mapping for testing."""

from datetime import datetime
from typing import Self
from uuid import UUID

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table
from tests.apps.models.user import User


@Table(User)
class UserTable(AbstractMappableTable[User]):
    """ORM table mapping for User domain entity."""

    __tablename__ = "users"

    uid: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    @classmethod
    def from_domain(cls, domain: User) -> Self:
        """Convert User domain entity to UserTable ORM object.

        Args:
            domain: User domain entity.

        Returns:
            UserTable ORM instance.
        """
        return cls(
            uid=domain.uid,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            username=domain.username,
            email=domain.email,
            password_hash=domain.password_hash,
        )

    def to_domain(self) -> User:
        """Convert UserTable ORM object to User domain entity.

        Returns:
            User domain entity.
        """
        return User(
            uid=self.uid,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            username=self.username,
            email=self.email,
            password_hash=self.password_hash,
        )
