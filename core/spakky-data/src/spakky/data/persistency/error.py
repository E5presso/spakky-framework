from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyPersistencyError(AbstractSpakkyFrameworkError, ABC):
    """Base error for persistency layer operations."""
