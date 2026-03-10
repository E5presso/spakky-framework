"""ORM table mappings for testing spakky-sqlalchemy plugin."""

from tests.apps.orm.comment import CommentTable
from tests.apps.orm.post import PostTable
from tests.apps.orm.user import UserTable

__all__ = [
    "CommentTable",
    "PostTable",
    "UserTable",
]
