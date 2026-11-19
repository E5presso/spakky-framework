"""Data persistence abstractions.

This module provides:
- Repository pattern interfaces
- Transaction management
- Persistence-related errors
"""

from spakky.data.persistency.error import (
    AbstractSpakkyPersistencyError,
    AggregateBufferNotOpenError,
    TransactionNotActiveError,
    TransactionRollbackOnlyError,
)
from spakky.data.persistency.repository import (
    EntityAlreadyExistsError,
    EntityNotFoundError,
    IGenericRepository,
)
from spakky.data.persistency.transaction import (
    AbstractAsyncTransaction,
    AbstractTransaction,
    Propagation,
)

__all__ = [
    # Repository
    "EntityAlreadyExistsError",
    "EntityNotFoundError",
    "IGenericRepository",
    # Transaction
    "AbstractAsyncTransaction",
    "AbstractTransaction",
    "Propagation",
    # Errors
    "AbstractSpakkyPersistencyError",
    "AggregateBufferNotOpenError",
    "TransactionNotActiveError",
    "TransactionRollbackOnlyError",
]
