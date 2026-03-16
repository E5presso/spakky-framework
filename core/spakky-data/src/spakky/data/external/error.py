from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyExternalError(AbstractSpakkyFrameworkError, ABC):
    """Base error for external proxy operations."""
