"""Errors for SQLAlchemy-backed agent persistence."""

from spakky.plugins.sqlalchemy.persistency.error import (
    AbstractSpakkySqlAlchemyPersistencyError,
)


class AgentPersistenceRowNotFoundError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when an agent persistence row cannot be found."""

    message = "Agent persistence row not found"


class AgentSignalTransactionMissingError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when a staged agent signal has no transaction to commit with."""

    message = "Agent signal append has no open transaction"


class AgentDocumentCorruptedError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when stored document rows do not form exactly one JSON value."""

    message = "Agent document rows do not form one JSON value"
