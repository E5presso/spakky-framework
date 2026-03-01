"""UserRole domain model with composite primary key."""

from dataclasses import field
from datetime import datetime
from uuid import UUID

from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.aggregate_root import AbstractAggregateRoot


@mutable
class UserRole(AbstractAggregateRoot[tuple[UUID, UUID]]):
    """User-Role association with composite primary key (user_id, role_id)."""

    user_id: UUID
    role_id: UUID
    assigned_at: datetime
    uid: tuple[UUID, UUID] = field(init=False)

    def __post_init__(self) -> None:
        self.uid = (self.user_id, self.role_id)

    @classmethod
    def next_id(cls) -> tuple[UUID, UUID]:
        return (uuid7(), uuid7())

    def validate(self) -> None:
        pass

    @classmethod
    def create(
        cls,
        user_id: UUID,
        role_id: UUID,
    ) -> "UserRole":
        """Create a new UserRole instance."""
        now = datetime.now()
        return cls(
            user_id=user_id,
            role_id=role_id,
            version=uuid7(),
            created_at=now,
            updated_at=now,
            assigned_at=now,
        )
