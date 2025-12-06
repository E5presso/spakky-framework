"""Password encoding protocol interface.

Defines the protocol interface for password hashing implementations
used by various password encoding algorithms.
"""

from abc import ABC, abstractmethod

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.interfaces.representable import IRepresentable


class IPasswordEncoder(IEquatable, IRepresentable, ABC):
    """Protocol for password hashing and verification operations."""

    @abstractmethod
    def encode(self) -> str: ...

    @abstractmethod
    def challenge(self, password: str) -> bool: ...
