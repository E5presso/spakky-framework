"""Outbox SQLAlchemy error classes."""

from abc import ABC

from spakky.plugins.outbox.error import AbstractSpakkyOutboxError


class AbstractSpakkyOutboxSqlAlchemyError(AbstractSpakkyOutboxError, ABC):
    """Base exception for Spakky Outbox SQLAlchemy errors."""

    ...
