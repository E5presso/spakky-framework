"""Extractor for SQLAlchemy ORM metadata."""

import datetime
import decimal
import enum
import uuid
from dataclasses import MISSING, Field, dataclass, fields
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    get_origin,
    get_type_hints,
)

from spakky.core.common.types import is_optional, remove_none
from spakky.core.pod.annotations.pod import Pod
from spakky.core.utils.naming import is_public_name

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint
from spakky.plugins.sqlalchemy.orm.error import AbstractSpakkyORMError
from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField
from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean
from spakky.plugins.sqlalchemy.orm.fields.datetime import Date, DateTime, Time
from spakky.plugins.sqlalchemy.orm.fields.enum import Enum as EnumField
from spakky.plugins.sqlalchemy.orm.fields.json import JSON
from spakky.plugins.sqlalchemy.orm.fields.numeric import Float, Integer, Numeric
from spakky.plugins.sqlalchemy.orm.fields.string import String
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid
from spakky.plugins.sqlalchemy.orm.table import Table


@dataclass
class ColumnInfo:
    """Extracted column information."""

    name: str
    field_metadata: AbstractField[Any]
    constraints: list[AbstractConstraint]
    python_type: Any
    default: Any = None
    default_factory: Callable[[], Any] | None = None
    nullable: bool = False


@dataclass
class ModelInfo:
    """Extracted model information."""

    table_name: str
    columns: dict[str, ColumnInfo]


class TableDefinitionNotFoundError(AbstractSpakkyORMError):
    """Raised when no Table definition is found on an entity class."""

    message: ClassVar[str] = "No Table definition found on entity class."


@Pod()
class Extractor:
    """Extracts SQLAlchemy model information from entity classes."""

    def extract(self, entity_cls: type) -> ModelInfo:
        """Extract metadata from an entity class.

        Args:
            entity_cls: The entity class to extract metadata from.

        Returns:
            ModelInfo: The extracted model information.
        """
        table_annotation = Table.get_or_none(entity_cls)
        if table_annotation is None:
            raise TableDefinitionNotFoundError

        columns: dict[str, ColumnInfo] = {}
        type_hints: dict[str, Any] = get_type_hints(entity_cls, include_extras=True)
        dataclass_fields: dict[str, Field[Any]] = {
            f.name: f for f in fields(entity_cls)
        }

        for name, field_type in (
            (n, t)
            for n, t in type_hints.items()
            if n in dataclass_fields and is_public_name(n)
        ):
            dataclass_field: Field[Any] = dataclass_fields[name]

            actual_type: type[Any | None] = field_type
            field_metadata: AbstractField[Any] | None = None
            constraints: list[AbstractConstraint] = []

            if get_origin(field_type) is Annotated:
                actual_type = AbstractField.get_actual_type(field_type)
                field_metadata = AbstractField.get_or_none(field_type)
                constraints = AbstractConstraint.all(field_type)

            nullable: bool = is_optional(actual_type)
            if nullable:
                actual_type = remove_none(actual_type)

            if field_metadata is None:
                field_metadata = self._infer_field_type(actual_type)

            columns[name] = ColumnInfo(
                name=name,
                field_metadata=field_metadata,
                constraints=constraints,
                python_type=actual_type,
                default=(
                    dataclass_field.default
                    if dataclass_field.default is not MISSING
                    else None
                ),
                default_factory=(
                    dataclass_field.default_factory
                    if dataclass_field.default_factory is not MISSING
                    else None
                ),
                nullable=nullable,
            )

        return ModelInfo(table_name=table_annotation.table_name, columns=columns)

    def _infer_field_type(self, type_hint: type[Any]) -> AbstractField[Any]:
        """Infer AbstractField from Python type."""
        if type_hint is int:
            return Integer()
        if type_hint is float:
            return Float()
        if type_hint is str:
            return String()
        if type_hint is bool:
            return Boolean()
        if type_hint is datetime.datetime:
            return DateTime()
        if type_hint is datetime.date:
            return Date()
        if type_hint is datetime.time:
            return Time()
        if type_hint is uuid.UUID:
            return Uuid()
        if type_hint is decimal.Decimal:
            return Numeric()
        if type_hint is bytes:
            return Binary()

        origin: Any | None = get_origin(type_hint)
        if origin in (dict, list) or type_hint in (dict, list):
            return JSON()

        if issubclass(type_hint, enum.Enum):
            return EnumField(enum_class=type_hint)

        # Fallback
        return String()
