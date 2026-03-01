"""UserRole repository with composite primary key support."""

from uuid import UUID

from spakky.data.stereotype.repository import Repository

from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
)
from tests.apps.models.user_role import UserRole


@Repository()
class UserRoleRepository(AbstractGenericRepository[UserRole, tuple[UUID, UUID]]):
    """Sync repository for UserRole with composite primary key."""

    pass


@Repository()
class AsyncUserRoleRepository(
    AbstractAsyncGenericRepository[UserRole, tuple[UUID, UUID]]
):
    """Async repository for UserRole with composite primary key."""

    pass
