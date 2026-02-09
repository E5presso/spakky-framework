"""Type mapper for converting field metadata to SQLAlchemy types."""

from enum import Enum
from typing import Any, TypeVar, cast

from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.sqlalchemy.orm.constraints.base import AbstractConstraint
from spakky.plugins.sqlalchemy.orm.constraints.foreign_key import (
    ForeignKey,
    ReferentialAction,
)
from spakky.plugins.sqlalchemy.orm.constraints.index import Index
from spakky.plugins.sqlalchemy.orm.constraints.primary_key import PrimaryKey
from spakky.plugins.sqlalchemy.orm.constraints.unique import Unique
from spakky.plugins.sqlalchemy.orm.extractor import ColumnInfo
from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField
from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
from spakky.plugins.sqlalchemy.orm.fields.boolean import Boolean as BooleanField
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    Date as DateField,
)
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    DateTime as DateTimeField,
)
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    Interval as IntervalField,
)
from spakky.plugins.sqlalchemy.orm.fields.datetime import (
    Time as TimeField,
)
from spakky.plugins.sqlalchemy.orm.fields.enum import EnumField
from spakky.plugins.sqlalchemy.orm.fields.json import JSON as JSONField
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    BigInteger as BigIntegerField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    Float as FloatField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    Integer as IntegerField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    Numeric as NumericField,
)
from spakky.plugins.sqlalchemy.orm.fields.numeric import (
    SmallInteger as SmallIntegerField,
)
from spakky.plugins.sqlalchemy.orm.fields.string import String as StringField
from spakky.plugins.sqlalchemy.orm.fields.text import Text as TextField
from spakky.plugins.sqlalchemy.orm.fields.uuid import Uuid as UuidField
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    Interval,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    Uuid,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    ForeignKey as SAForeignKey,
)
from sqlalchemy.sql.type_api import TypeEngine

_ConstraintT = TypeVar("_ConstraintT", bound=AbstractConstraint)

DEFAULT_STRING_LENGTH: int = 255
"""Default length for fallback String column type."""


@Pod()
class TypeMapper:
    """Maps field metadata to SQLAlchemy column definitions.

    Converts Spakky ORM field annotations and constraints into
    SQLAlchemy Column objects with the appropriate types and options.

    This is a singleton Pod that provides the mapping logic for
    the ModelRegistry.
    """

    # Any: SQLAlchemy Column is invariant, actual type varies at runtime
    def create_column(self, name: str, col_info: ColumnInfo) -> Column[Any]:
        """Create a SQLAlchemy Column from column info.

        Args:
            name: The column name.
            col_info: Extracted column information.

        Returns:
            SQLAlchemy Column object with appropriate type and constraints.
        """
        sa_type = self._map_type(col_info.field_metadata)
        column_name = col_info.field_metadata.name or name

        # Extract constraint info
        primary_key_constraint = self._get_constraint(col_info, PrimaryKey)
        unique_constraint = self._get_constraint(col_info, Unique)
        index_constraint = self._get_constraint(col_info, Index)

        # Determine default value
        default = (
            col_info.default
            if col_info.default is not None
            else (
                col_info.default_factory
                if col_info.default_factory is not None
                else None
            )
        )

        # Determine column-level unique/index
        # Named constraints are handled at table level, not column level
        column_unique = (
            True
            if unique_constraint is not None and unique_constraint.name is None
            else None
        )
        column_index = (
            True
            if index_constraint is not None
            and index_constraint.name is None
            and not index_constraint.unique
            else None
        )

        # Handle foreign key constraint
        foreign_key = self._get_foreign_key(col_info)
        if foreign_key is not None:
            return Column(
                column_name,
                sa_type,
                foreign_key,
                nullable=col_info.nullable,
                primary_key=primary_key_constraint is not None,
                autoincrement=(
                    primary_key_constraint.autoincrement
                    if primary_key_constraint is not None
                    else "auto"
                ),
                unique=column_unique,
                index=column_index,
                default=default,
                comment=col_info.field_metadata.comment,
            )

        return Column(
            column_name,
            sa_type,
            nullable=col_info.nullable,
            primary_key=primary_key_constraint is not None,
            autoincrement=(
                primary_key_constraint.autoincrement
                if primary_key_constraint is not None
                else "auto"
            ),
            unique=column_unique,
            index=column_index,
            default=default,
            comment=col_info.field_metadata.comment,
        )

    def _map_type(  # noqa: PLR0911
        self, field_meta: AbstractField[object]
    ) -> TypeEngine[Any]:  # Any: SQLAlchemy TypeEngine is invariant, actual type varies
        """Map field metadata to SQLAlchemy type.

        Args:
            field_meta: The field metadata annotation.

        Returns:
            SQLAlchemy type class or instance.
        """
        match field_meta:
            case IntegerField():
                return Integer()
            case BigIntegerField():
                return BigInteger()
            case SmallIntegerField():
                return SmallInteger()
            case FloatField():
                return Float(
                    precision=field_meta.precision,
                    asdecimal=field_meta.asdecimal,
                    decimal_return_scale=field_meta.decimal_return_scale,
                )
            case NumericField():
                return Numeric(
                    precision=field_meta.precision,
                    scale=field_meta.scale,
                    decimal_return_scale=field_meta.decimal_return_scale,
                    asdecimal=field_meta.asdecimal,
                )
            case StringField():
                return String(
                    length=field_meta.length,
                    collation=field_meta.collation,
                )
            case TextField():
                return Text(collation=field_meta.collation)
            case BooleanField():
                return Boolean()
            case DateField():
                return Date()
            case DateTimeField():
                return DateTime(timezone=field_meta.timezone)
            case TimeField():
                return Time(timezone=field_meta.timezone)
            case IntervalField():
                return Interval(
                    native=field_meta.native,
                    second_precision=field_meta.second_precision,
                    day_precision=field_meta.day_precision,
                )
            case UuidField():
                return Uuid(
                    as_uuid=field_meta.as_uuid,
                    native_uuid=field_meta.native_uuid,
                )
            case JSONField():
                return JSON(none_as_null=field_meta.none_as_null)
            case Binary():
                return LargeBinary(length=field_meta.length)
            case EnumField():
                return SAEnum(
                    cast(type[Enum], field_meta.enum_class),
                    native_enum=field_meta.native_enum,
                )
            case _:
                # Default fallback for unknown types
                return String(length=DEFAULT_STRING_LENGTH)

    def _get_constraint(
        self, col_info: ColumnInfo, constraint_type: type[_ConstraintT]
    ) -> _ConstraintT | None:
        """Get a specific constraint from column info.

        Args:
            col_info: Column information.
            constraint_type: The constraint class to look for.

        Returns:
            The constraint instance or None.
        """
        for constraint in col_info.constraints:
            if isinstance(constraint, constraint_type):
                return constraint
        return None

    def _get_foreign_key(self, col_info: ColumnInfo) -> SAForeignKey | None:
        """Get foreign key constraint if present.

        Args:
            col_info: Column information.

        Returns:
            SQLAlchemy ForeignKey object or None.
        """
        fk = self._get_constraint(col_info, ForeignKey)
        if fk is None:
            return None

        return SAForeignKey(
            fk.column,
            name=fk.name,
            ondelete=(
                self._map_referential_action(fk.on_delete)
                if fk.on_delete is not None
                else None
            ),
            onupdate=(
                self._map_referential_action(fk.on_update)
                if fk.on_update is not None
                else None
            ),
        )

    def _map_referential_action(self, action: ReferentialAction) -> str:
        """Map ReferentialAction to SQL string.

        Args:
            action: The referential action enum value.

        Returns:
            SQL action string.
        """
        return action.value
