"""Spakky Data package - Data access abstractions.

This package provides:
- Repository pattern for aggregate persistence
- Transaction management
- External service proxy pattern

Usage:
    from spakky.data import IGenericRepository, AbstractTransaction
    from spakky.data import IGenericProxy, IAsyncGenericProxy
"""

# Persistency
# External
from spakky.data.external.error import AbstractSpakkyExternalError
from spakky.data.external.proxy import IAsyncGenericProxy, IGenericProxy
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
