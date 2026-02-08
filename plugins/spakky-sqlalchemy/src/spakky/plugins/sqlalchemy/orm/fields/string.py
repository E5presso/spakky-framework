from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class String(AbstractField[str]):
    """Metadata annotation for string fields in SQLAlchemy ORM."""

    length: int = 255
    """The maximum length of the string field."""
