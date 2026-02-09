"""Constraint metadata for SQLAlchemy ORM.

This module provides metadata annotations for database constraints
such as primary keys, foreign keys, indexes, and unique constraints.
"""

from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import ForeignKey
from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique

__all__ = [
    "ForeignKey",
    "Index",
    "PrimaryKey",
    "Unique",
]
