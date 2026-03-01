from uuid import UUID

from spakky.data.stereotype.repository import Repository

from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
)
from tests.apps.models.user import User


@Repository()
class UserRepository(AbstractGenericRepository[User, UUID]):
    pass


@Repository()
class AsyncUserRepository(AbstractAsyncGenericRepository[User, UUID]):
    pass
