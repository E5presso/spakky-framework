"""Celery plugin error hierarchy."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyCeleryError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky Celery errors."""

    ...
