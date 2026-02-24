"""Spakky Data package - Data access abstractions.

# CI test - verify partial package testing

This package provides:
- Repository pattern for aggregate persistence
- Transaction management
- External service proxy pattern

Usage:
    from spakky.data import IGenericRepository, AbstractTransaction
    from spakky.data import IGenericProxy, IAsyncGenericProxy
"""

# External
from spakky.data.external.error import AbstractSpakkyExternalError
from spakky.data.external.proxy import IAsyncGenericProxy, IGenericProxy

# Persistency
from spakky.data.persistency.error import AbstractSpakkyPersistencyError
from spakky.data.persistency.repository import (
    EntityNotFoundError,
    IGenericRepository,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
)

__all__ = [
    # Repository
    "EntityNotFoundError",
    "IGenericRepository",
    # Transaction
    "AbstractAsyncTransaction",
    "AbstractTransaction",
    # Proxy
    "IAsyncGenericProxy",
    "IGenericProxy",
    # Errors
    "AbstractSpakkyExternalError",
    "AbstractSpakkyPersistencyError",
]

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-data")
"""Plugin identifier for the Spakky Data package."""
