from uuid import UUID

from spakky.data.stereotype.repository import Repository

from spakky.plugins.sqlalchemy.persistency.repository import (
    AbstractAsyncGenericRepository,
    AbstractGenericRepository,
)
from tests.apps.models.comment import Comment


@Repository()
class CommentRepository(AbstractGenericRepository[Comment, UUID]):
    pass


@Repository()
class AsyncCommentRepository(AbstractAsyncGenericRepository[Comment, UUID]):
    pass
