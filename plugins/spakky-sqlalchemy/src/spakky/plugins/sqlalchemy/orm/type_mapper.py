"""Type mapper for converting field metadata to SQLAlchemy types."""

from typing import Any

from spakky.core.pod.annotations.pod import Pod

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
from spakky.plugins.sqlalchemy.orm.fields.enum import Enum as EnumField
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


@Pod()
class TypeMapper:
    """Maps field metadata to SQLAlchemy column definitions.

    Converts Spakky ORM field annotations and constraints into
    SQLAlchemy Column objects with the appropriate types and options.

    This is a singleton Pod that provides the mapping logic for
    the ModelRegistry.
    """

    def create_column(self, name: str, col_info: ColumnInfo) -> Column[Any]:
        """Create a SQLAlchemy Column from column info.

        Args:
            name: The column name.
            col_info: Extracted column information.

        Returns:
            SQLAlchemy Column object with appropriate type and constraints.
        """
        sa_type = self._map_type(col_info.field_metadata)
        column_kwargs = self._build_column_kwargs(col_info)

        # Handle foreign key constraint
        foreign_key = self._get_foreign_key(col_info)
        if foreign_key is not None:
            return Column(
                col_info.field_metadata.name or name,
                sa_type,
                foreign_key,
                **column_kwargs,
            )

        return Column(
            col_info.field_metadata.name or name,
            sa_type,
            **column_kwargs,
        )

    def _map_type(self, field_meta: AbstractField[Any]) -> Any:
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
                kwargs: dict[str, Any] = {}
                if field_meta.precision is not None:
                    kwargs["precision"] = field_meta.precision
                if field_meta.decimal_return_scale is not None:
                    kwargs["decimal_return_scale"] = field_meta.decimal_return_scale
                return Float(**kwargs)
            case NumericField():
                kwargs: dict[str, Any] = {}
                if field_meta.precision is not None:
                    kwargs["precision"] = field_meta.precision
                if field_meta.scale is not None:
                    kwargs["scale"] = field_meta.scale
                kwargs["asdecimal"] = field_meta.asdecimal
                return Numeric(**kwargs)
            case StringField():
                return String(length=field_meta.length)
            case TextField():
                kwargs: dict[str, Any] = {}
                if field_meta.collation is not None:
                    kwargs["collation"] = field_meta.collation
                return Text(**kwargs)
            case BooleanField():
                return Boolean()
            case DateField():
                return Date()
            case DateTimeField():
                return DateTime(timezone=field_meta.timezone)
            case TimeField():
                return Time(timezone=field_meta.timezone)
            case IntervalField():
                return Interval()
            case UuidField():
                return Uuid(as_uuid=field_meta.as_uuid)
            case JSONField():
                return JSON()
            case Binary():
                kwargs: dict[str, Any] = {}
                if field_meta.length is not None:
                    kwargs["length"] = field_meta.length
                return LargeBinary(**kwargs)
            case EnumField():
                return SAEnum(
                    field_meta.enum_class,
                    native_enum=field_meta.native_enum,
                )
            case _:
                # Default fallback for unknown types
                return String(length=255)

    def _build_column_kwargs(self, col_info: ColumnInfo) -> dict[str, Any]:
        """Build keyword arguments for Column constructor.

        Args:
            col_info: Extracted column information.

        Returns:
            Dictionary of keyword arguments for Column.
        """
        kwargs: dict[str, Any] = {
            "nullable": col_info.nullable,
        }

        # Handle primary key
        primary_key = self._get_constraint(col_info, PrimaryKey)
        if primary_key is not None:
            kwargs["primary_key"] = True
            kwargs["autoincrement"] = primary_key.autoincrement

        # Handle unique constraint
        unique = self._get_constraint(col_info, Unique)
        if unique is not None:
            kwargs["unique"] = True

        # Handle index
        index = self._get_constraint(col_info, Index)
        if index is not None:
            kwargs["index"] = True

        # Handle default value
        if col_info.default is not None:
            kwargs["default"] = col_info.default
        elif col_info.default_factory is not None:
            kwargs["default"] = col_info.default_factory

        # Handle comment
        if col_info.field_metadata.comment is not None:
            kwargs["comment"] = col_info.field_metadata.comment

        return kwargs

    def _get_constraint(
        self, col_info: ColumnInfo, constraint_type: type
    ) -> Any | None:
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

        kwargs: dict[str, Any] = {}
        if fk.name is not None:
            kwargs["name"] = fk.name
        if fk.on_delete is not None:
            kwargs["ondelete"] = self._map_referential_action(fk.on_delete)
        if fk.on_update is not None:
            kwargs["onupdate"] = self._map_referential_action(fk.on_update)

        return SAForeignKey(fk.column, **kwargs)

    def _map_referential_action(self, action: ReferentialAction) -> str:
        """Map ReferentialAction to SQL string.

        Args:
            action: The referential action enum value.

        Returns:
            SQL action string.
        """
        return action.value
