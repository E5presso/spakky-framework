"""Entity model for domain-driven design.

This module provides AbstractEntity base class for DDD entities with
identity, validation, and immutability enforcement.
"""

from abc import ABC, abstractmethod
from dataclasses import field
from datetime import UTC, datetime
from typing import Any, Generic
from uuid import UUID, uuid4

from spakky.core.interfaces.equatable import EquatableT, IEquatable
from spakky.core.mutability import mutable
from spakky.domain.error import AbstractSpakkyDomainError


class CannotMonkeyPatchEntityError(AbstractSpakkyDomainError):
    """Raised when attempting to add attributes not defined in the entity schema."""

    message = "Cannot monkey patch an entity."


@mutable
class AbstractEntity(IEquatable, Generic[EquatableT], ABC):
    """Base class for DDD entities with identity and validation.

    Entities are objects with unique identity that maintain consistency
    through validation and prevent unauthorized modifications.
    """

    __initialized: bool = field(init=False, repr=False, default=False)

    uid: EquatableT
    """Unique identifier for this entity."""

    version: UUID = field(default_factory=uuid4)
    """Version identifier for optimistic locking."""

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Timestamp when entity was created."""

    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Timestamp when entity was last updated."""

    @classmethod
    @abstractmethod
    def next_id(cls) -> EquatableT:
        """Generate next unique identifier for this entity type.

        Returns:
            New unique identifier.
        """
        ...

    @abstractmethod
    def validate(self) -> None:
        """Validate entity state.

        Raises:
            AbstractDomainValidationError: If validation fails.
        """
        ...

    def __eq__(self, other: object) -> bool:
        """Compare entities by identity.

        Args:
            other: Object to compare with.

        Returns:
            True if same entity type and uid.
        """
        if not isinstance(other, type(self)):
            return False
        return self.uid == other.uid

    def __hash__(self) -> int:
        """Compute hash based on entity identity.

        Returns:
            Hash of uid.
        """
        return hash(self.uid)

    def __post_init__(self) -> None:
        """Validate entity after initialization."""
        self.validate()
        self.__initialized = True

    def __setattr__(self, __name: str, __value: Any) -> None:
        """Set attribute with validation and rollback on failure.

        Args:
            __name: Attribute name.
            __value: New value.

        Raises:
            CannotMonkeyPatchEntityError: If attribute not in schema.
        """
        if __name not in self.__dataclass_fields__:
            raise CannotMonkeyPatchEntityError
        __old: Any | None = getattr(self, __name, None)
        super().__setattr__(__name, __value)
        if self.__initialized:
            try:
                self.validate()
            except:
                super().__setattr__(__name, __old)
                raise
