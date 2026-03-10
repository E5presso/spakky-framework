from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkySqlAlchemyError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky SQLAlchemy errors."""
