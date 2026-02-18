from abc import ABC

from spakky.plugins.sqlalchemy.error import AbstractSpakkySqlAlchemyError


class AbstractSpakkySqlAlchemyORMError(AbstractSpakkySqlAlchemyError, ABC):
    """Base exception for Spakky SQLAlchemy ORM errors."""
