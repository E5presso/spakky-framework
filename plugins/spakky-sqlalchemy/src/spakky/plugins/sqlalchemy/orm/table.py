"""Table annotation for SQLAlchemy ORM."""

from dataclasses import dataclass

from spakky.core.common.annotation import ClassAnnotation
from spakky.core.common.types import ObjectT
from spakky.core.utils.casing import pascal_to_snake


@dataclass
class Table(ClassAnnotation):
    """Annotation representing a database table.

    Use as a decorator on dataclass types to mark them as database tables.
    Automatically generates table names from class names using snake_case.

    Examples:
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class UserAccount:  # table name: "user_account"
        ...     id: int
        ...     username: str
        >>>
        >>> @Table(name="users")  # custom table name
        >>> @dataclass
        >>> class User:
        ...     id: int
    """

    name: str = ""
    """The name of the database table.

    If empty, automatically generated from class name using snake_case.
    """

    def __call__(self, obj: type[ObjectT]) -> type[ObjectT]:
        if not hasattr(obj, "__dataclass_fields__"):
            raise TypeError("Table annotation can only be applied to dataclass types.")
        if not self.name:
            self.name = pascal_to_snake(obj.__name__)
        return super().__call__(obj)
