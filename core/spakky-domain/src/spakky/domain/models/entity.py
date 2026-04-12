"""Entity model for domain-driven design.

This module provides AbstractEntity base class for DDD entities with
identity, validation, and immutability enforcement.
"""

import sys
from abc import ABC, abstractmethod
from dataclasses import field
from datetime import UTC, datetime
from typing import Any, ClassVar, Generic
from uuid import UUID

if (
    sys.version_info
    >= (
        3,
        12,
    )
):  # pragma: no cover - Python 3.12+ import path; coverage may run on a single interpreter
    from typing import override
else:
    from typing_extensions import override

from spakky.core.common.interfaces.equatable import EquatableT, IEquatable
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7

from spakky.domain.error import AbstractSpakkyDomainError
from spakky.domain.models.base import AbstractDomainModel


class CannotMonkeyPatchEntityError(AbstractSpakkyDomainError):
    """Raised when attempting to add attributes not defined in the entity schema."""

    message = "Cannot monkey patch an entity."


@mutable
class AbstractEntity(AbstractDomainModel, IEquatable, Generic[EquatableT], ABC):
    """Base class for DDD entities with identity and validation.

    Entities are objects with unique identity that maintain consistency
    through validation and prevent unauthorized modifications.
    """

    # Fields excluded from auto-update (do not trigger updated_at/version changes)
    _AUTO_UPDATE_EXCLUDE_FIELDS: ClassVar[set[str]] = {
        "uid",
        "version",
        "created_at",
        "updated_at",
        "_AbstractEntity__initialized",
    }

    __initialized: bool = field(init=False, repr=False, default=False)

    uid: EquatableT
    """Unique identifier for this entity."""

    version: UUID = field(default_factory=uuid7)
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

    @override
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

    @override
    def __hash__(self) -> int:
        """Compute hash based on entity identity.

        Returns:
            Hash of uid.
        """
        return hash(self.uid)

    @override
    def __post_init__(self) -> None:
        """Validate entity after initialization."""
        self.validate()
        self.__initialized = True

    def __setattr__(self, __name: str, __value: Any) -> None:
        """Set attribute with validation and rollback on failure.

        Automatically updates `updated_at` and `version` when any attribute
        (except metadata fields) is modified after initialization.

        Args:
            __name: Attribute name.
            __value: New value.

        Raises:
            CannotMonkeyPatchEntityError: If attribute not in schema.
        """
        if __name not in self.__dataclass_fields__:
            raise CannotMonkeyPatchEntityError
        __old: Any | None = getattr(
            self, __name, None
        )  # 프레임워크 내부: 도메인 모델 변경 추적
        super().__setattr__(__name, __value)
        if self.__initialized:
            try:
                self.validate()
                # Auto-update metadata fields when business attributes change
                if __name not in self._AUTO_UPDATE_EXCLUDE_FIELDS:
                    super().__setattr__("updated_at", datetime.now(UTC))
                    super().__setattr__("version", uuid7())
            except:
                super().__setattr__(__name, __old)
                raise
