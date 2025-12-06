"""CQRS application layer interfaces.

This module provides base interfaces for Command Query Responsibility Segregation:
- AbstractCommand: Base class for command DTOs
- AbstractQuery: Base class for query DTOs
- ICommandUseCase: Interface for command handlers
- IQueryUseCase: Interface for query handlers
"""

from spakky.domain.application.command import (
    AbstractCommand,
    ICommandUseCase,
)
from spakky.domain.application.query import (
    AbstractQuery,
    IQueryUseCase,
)

__all__ = [
    "AbstractCommand",
    "AbstractQuery",
    "ICommandUseCase",
    "IQueryUseCase",
]
