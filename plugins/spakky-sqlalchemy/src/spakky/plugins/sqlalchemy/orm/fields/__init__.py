"""Field metadata annotations for SQLAlchemy ORM.

This module provides type-safe field metadata for defining database columns
using Python type hints and Annotated types.
"""

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField
from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean
from spakky.plugins.sqlalchemy.orm.fields.datetime import Date, DateTime, Interval, Time
from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
from spakky.plugins.sqlalchemy.orm.fields.json import JSON
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    BigInteger,
    Float,
    Integer,
    Numeric,
    SmallInteger,
)
from spakky.plugins.sqlalchemy.orm.fields.string import String
from spakky.plugins.sqlalchemy.orm.fields.text import Text
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid

__all__ = [
    "AbstractField",
    # Numeric types
    "Integer",
    "BigInteger",
    "SmallInteger",
    "Float",
    "Numeric",
    # String types
    "String",
    "Text",
    # Date/Time types
    "Date",
    "DateTime",
    "Time",
    "Interval",
    # Other types
    "Binary",
    "Boolean",
    "JSON",
    "Uuid",
    "EnumField",
]
