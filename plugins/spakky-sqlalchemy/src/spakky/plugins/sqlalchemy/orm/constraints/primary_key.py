"""Primary key constraint metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint


@mutable
class PrimaryKey(AbstractConstraint):
    """Primary key constraint metadata.

    Marks a field as a primary key column in SQLAlchemy ORM.
    Maps directly to SQLAlchemy Column's primary_key parameter.
    """

    autoincrement: bool = False
    """Whether to enable autoincrement for this primary key."""
