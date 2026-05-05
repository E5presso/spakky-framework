"""Errors for SQLAlchemy-backed agent persistence."""

from spakky.plugins.sqlalchemy.persistency.error import (
    AbstractSpakkySqlAlchemyPersistencyError,
)


class AgentPersistenceRowNotFoundError(AbstractSpakkySqlAlchemyPersistencyError):
    """Raised when an agent persistence row cannot be found."""

    message = "Agent persistence row not found"
