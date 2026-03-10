from uuid import UUID

from spakky.data.stereotype.repository import Repository

from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
)
from tests.apps.models.post import Post


@Repository()
class PostRepository(AbstractGenericRepository[Post, UUID]):
    pass


@Repository()
class AsyncPostRepository(AbstractAsyncGenericRepository[Post, UUID]):
    pass
