"""Numeric field metadata for SQLAlchemy ORM."""

from decimal import Decimal

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class Integer(AbstractField[int]):
    """Metadata annotation for integer fields.

    Maps to SQLAlchemy's Integer type.
    """


@mutable
class BigInteger(AbstractField[int]):
    """Metadata annotation for big integer fields.

    Maps to SQLAlchemy's BigInteger type for large integer values.
    """


@mutable
class SmallInteger(AbstractField[int]):
    """Metadata annotation for small integer fields.

    Maps to SQLAlchemy's SmallInteger type for small integer values.
    """


@mutable
class Float(AbstractField[float]):
    """Metadata annotation for floating-point fields.

    Maps to SQLAlchemy's Float type.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.numeric import Float
        >>>
        >>> class Product:
        ...     price: Annotated[float, Float(precision=10)]
        ...     weight: Annotated[float, Float(precision=5, decimal_return_scale=2)]
    """

    precision: int | None = None
    """Total number of digits."""

    asdecimal: bool = False
    """Return values as Decimal objects (True) or float (False)."""

    decimal_return_scale: int | None = None
    """Number of decimal places to return."""


@mutable
class Numeric(AbstractField[Decimal]):
    """Metadata annotation for precise decimal fields.

    Maps to SQLAlchemy's Numeric type. Use for financial calculations
    where floating-point precision issues must be avoided.

    Examples:
        >>> from typing import Annotated
        >>> from decimal import Decimal
        >>> from spakky.plugins.sqlalchemy.orm.fields.numeric import Numeric
        >>>
        >>> class Transaction:
        ...     amount: Annotated[Decimal, Numeric(precision=10, scale=2)]
    """

    precision: int | None = None
    """Total number of digits."""

    scale: int | None = None
    """Number of decimal places."""

    decimal_return_scale: int | None = None
    """Number of decimal places to return."""

    asdecimal: bool = True
    """Return values as Decimal objects (True) or float (False)."""
