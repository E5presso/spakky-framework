"""Outbox error classes."""

from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyOutboxError(AbstractSpakkyFrameworkError, ABC):
    """Base exception for Spakky Outbox errors."""

    ...
