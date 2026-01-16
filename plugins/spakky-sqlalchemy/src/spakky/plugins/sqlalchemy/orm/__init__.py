"""ORM annotations, metadata, and extractors for SQLAlchemy mapping.

This module provides annotations, metadata, and extraction utilities for
customizing SQLAlchemy ORM mapping behavior.
"""

from spakky.plugins.sqlalchemy.orm.annotation import Table as Table
from spakky.plugins.sqlalchemy.orm.extractor import EntityMetadata as EntityMetadata
from spakky.plugins.sqlalchemy.orm.extractor import FieldMetadata as FieldMetadata
from spakky.plugins.sqlalchemy.orm.extractor import (
    MetadataExtractor as MetadataExtractor,
)
from spakky.plugins.sqlalchemy.orm.metadata import BinaryField as BinaryField
from spakky.plugins.sqlalchemy.orm.metadata import DateTimeField as DateTimeField
from spakky.plugins.sqlalchemy.orm.metadata import DecimalField as DecimalField
from spakky.plugins.sqlalchemy.orm.metadata import EnumField as EnumField
from spakky.plugins.sqlalchemy.orm.metadata import Field as Field
from spakky.plugins.sqlalchemy.orm.metadata import JsonField as JsonField
from spakky.plugins.sqlalchemy.orm.metadata import StringField as StringField
from spakky.plugins.sqlalchemy.orm.metadata import TextField as TextField
from spakky.plugins.sqlalchemy.orm.metadata import TimeField as TimeField
from spakky.plugins.sqlalchemy.orm.type_mapper import TypeMapper as TypeMapper

__all__ = [
    # Annotations
    "Table",
    # Field metadata
    "Field",
    "StringField",
    "TextField",
    "DecimalField",
    "BinaryField",
    "EnumField",
    "JsonField",
    "DateTimeField",
    "TimeField",
    # Extractor
    "EntityMetadata",
    "FieldMetadata",
    "MetadataExtractor",
    # Type mapping
    "TypeMapper",
]
