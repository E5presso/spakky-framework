"""Data persistence abstractions.

This module provides:
- Repository pattern interfaces
- Transaction management
- Persistence-related errors
"""

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
    # Errors
    "AbstractSpakkyPersistencyError",
]
