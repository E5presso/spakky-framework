from abc import ABC

from spakky.plugins.sqlalchemy.error import AbstractSpakkySqlAlchemyError


class AbstractSpakkyORMError(AbstractSpakkySqlAlchemyError, ABC):
    """Base exception for Spakky SQLAlchemy ORM errors."""


class InvalidTableTargetError(AbstractSpakkyORMError):
    """Error raised when @Table is applied to non-dataclass type.

    @Table annotation can only be applied to dataclass types.
    """

    message = "@Table annotation can only be applied to dataclass types"


class InvalidTableScopeError(AbstractSpakkyORMError):
    """Error raised when @Table annotated class has invalid scope.

    @Table annotated classes must use DEFINITION scope since they are
    metadata-only registrations and should not be instantiated as managed beans.
    """

    message = "@Table annotated classes must use DEFINITION scope"
