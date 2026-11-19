from abc import ABC

from spakky.core.common.error import AbstractSpakkyFrameworkError


class AbstractSpakkyPersistencyError(AbstractSpakkyFrameworkError, ABC):
    """Base error for persistency layer operations."""


class TransactionRollbackOnlyError(AbstractSpakkyPersistencyError):
    """Raised when a transaction marked rollback-only is asked to commit.

    A joined (``Propagation.REQUIRED``) inner scope that exits with an exception
    marks the whole physical transaction rollback-only. If the outermost scope
    then finishes normally, the transaction is rolled back instead of committed
    and this error is raised so the caller knows nothing was persisted.
    """

    message = "Transaction was marked rollback-only by an inner scope and has been rolled back."


class TransactionNotActiveError(AbstractSpakkyPersistencyError):
    """Raised when a transaction scope is closed while no scope is open."""

    message = "No transaction scope is active in the current context."


class TransactionAlreadyFinishedError(AbstractSpakkyPersistencyError):
    """Raised when a joined scope exits after the transaction it joined finished.

    A child task or thread that joined (``Propagation.REQUIRED``) a transaction
    of its parent can outlive the parent's scope. Once the scope that opened
    the physical transaction has committed or rolled back and released it,
    work done in the joined scope afterwards was not part of that transaction,
    so the joined scope fails loudly instead of losing it silently.
    """

    message = "The transaction this scope joined had already finished before the scope exited."


class AggregateBufferNotOpenError(AbstractSpakkyPersistencyError):
    """Raised when a transaction buffer is closed that was never opened."""

    message = "No transaction buffer is open in the aggregate collector."
