"""Table annotation for SQLAlchemy ORM."""

from dataclasses import dataclass, field
from typing import cast

from spakky.core.pod.annotations.pod import Pod, PodT
from spakky.core.utils.casing import pascal_to_snake

from spakky.plugins.sqlalchemy.orm.error import (
    InvalidTableScopeError,
    InvalidTableTargetError,
)


@dataclass(eq=False)
class Table(Pod):
    """Annotation representing a database table.

    Use as a decorator on dataclass types to mark them as database tables.
    Automatically generates table names from class names using snake_case.

    This extends Pod with DEFINITION scope, meaning the table definition
    is registered with the IoC container for discovery, but never instantiated.
    Post-processors can discover Table-annotated classes during startup.

    Examples:
        >>> from spakky.plugins.sqlalchemy.orm.table import Table
        >>>
        >>> @Table()
        >>> @dataclass
        >>> class UserAccount:  # table name: "user_account"
        ...     id: int
        ...     username: str
        >>>
        >>> @Table(table_name="users")  # custom table name
        >>> @dataclass
        >>> class User:
        ...     id: int
    """

    table_name: str = ""
    """The name of the database table.

    If empty, automatically generated from class name using snake_case.
    """

    scope: Pod.Scope = field(default=Pod.Scope.DEFINITION, kw_only=True)
    """The scope is fixed to DEFINITION for table definitions."""

    def __call__(self, obj: PodT) -> PodT:
        if not hasattr(obj, "__dataclass_fields__"):
            raise InvalidTableTargetError()
        if self.scope != Pod.Scope.DEFINITION:
            raise InvalidTableScopeError()
        if not self.table_name:
            self.table_name = pascal_to_snake(cast(type, obj).__name__)
        return super().__call__(obj)
