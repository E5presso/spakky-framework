"""UserRole ORM table mapping with composite primary key for testing."""

from datetime import datetime
from typing import Self
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from spakky.plugins.sqlalchemy.orm.table import AbstractMappableTable, Table
from tests.apps.models.user_role import UserRole


@Table(UserRole)
class UserRoleTable(AbstractMappableTable[UserRole]):
    """ORM table mapping for UserRole domain entity with composite primary key."""

    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("users.uid"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(True), nullable=False)

    @property
    def uid(self) -> tuple[UUID, UUID]:
        """Return composite primary key as tuple."""
        return (self.user_id, self.role_id)

    @classmethod
    def from_domain(cls, domain: UserRole) -> Self:
        """Convert UserRole domain entity to UserRoleTable ORM object.

        Args:
            domain: UserRole domain entity.

        Returns:
            UserRoleTable ORM instance.
        """
        return cls(
            user_id=domain.user_id,
            role_id=domain.role_id,
            version=domain.version,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            assigned_at=domain.assigned_at,
        )

    def to_domain(self) -> UserRole:
        """Convert UserRoleTable ORM object to UserRole domain entity.

        Returns:
            UserRole domain entity.
        """
        return UserRole(
            user_id=self.user_id,
            role_id=self.role_id,
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            assigned_at=self.assigned_at,
        )
