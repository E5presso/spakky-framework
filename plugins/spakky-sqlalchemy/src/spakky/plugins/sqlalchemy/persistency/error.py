from abc import ABC

from spakky.plugins.sqlalchemy.error import AbstractSpakkySqlAlchemyError


class AbstractSpakkySqlAlchemyPersistencyError(AbstractSpakkySqlAlchemyError, ABC):
    """Base exception for Spakky SQLAlchemy persistency errors."""
