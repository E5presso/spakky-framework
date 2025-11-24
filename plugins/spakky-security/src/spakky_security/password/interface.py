"""Password encoding protocol interface.

Defines the protocol interface for password hashing implementations
used by various password encoding algorithms.
"""

from abc import abstractmethod
from typing import Protocol, runtime_checkable

from spakky.core.interfaces.equatable import IEquatable
from spakky.core.interfaces.representable import IRepresentable


@runtime_checkable
class IPasswordEncoder(IEquatable, IRepresentable, Protocol):
    """Protocol for password hashing and verification operations."""

    @abstractmethod
    def encode(self) -> str: ...

    @abstractmethod
    def challenge(self, password: str) -> bool: ...
