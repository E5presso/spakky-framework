"""Entity model for domain-driven design.

This module provides AbstractEntity base class for DDD entities with
identity, validation, and immutability enforcement.
"""

from abc import ABC, abstractmethod
from dataclasses import field
from datetime import UTC, datetime
from typing import Any, ClassVar, override
from uuid import UUID

from spakky.core.common.interfaces.equatable import IEquatable
from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7

from spakky.domain.error import AbstractSpakkyDomainError
from spakky.domain.models.base import AbstractDomainModel


class CannotMonkeyPatchEntityError(AbstractSpakkyDomainError):
    """Raised when attempting to add attributes not defined in the entity schema."""

    message = "Cannot monkey patch an entity."


@mutable
class AbstractEntity[EquatableT](AbstractDomainModel, IEquatable, ABC):
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
        "_AbstractEntity__persisted_version",
    }

    __initialized: bool = field(init=False, repr=False, default=False)
    # None: `version` has not moved since construction or `mark_persisted()`,
    # so the stored version is `version` itself.
    __persisted_version: UUID | None = field(init=False, repr=False, default=None)

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

    @property
    def persisted_version(self) -> UUID:
        """Version this entity is known to have in its backing store.

        Business-field changes keep regenerating `version`, while this value
        stays at the version the entity was constructed with (the stored
        version for an entity rebuilt from persistence) until
        `mark_persisted()` is called. A repository compares this value with
        the stored version to detect concurrent writes.

        For an entity that has never been stored, this is simply its initial
        version, which no stored record can match.

        Returns:
            The version that the last known stored state carries.
        """
        if self.__persisted_version is None:
            return self.version
        return self.__persisted_version

    def mark_persisted(self) -> None:
        """Record that the current `version` is now the stored version.

        Repositories call this after a successful write so that the same
        instance can be changed and saved again within one use case.
        """
        self.__persisted_version = None

    def validate(self) -> None:
        """Validate entity state.

        Subclasses may override this method to enforce entity invariants.
        """
        return

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
                if __name == "version" and self.__persisted_version is None:
                    self.__persisted_version = __old
                if __name not in self._AUTO_UPDATE_EXCLUDE_FIELDS:
                    if self.__persisted_version is None:
                        self.__persisted_version = self.version
                    super().__setattr__("updated_at", datetime.now(UTC))
                    super().__setattr__("version", uuid7())
            except:
                super().__setattr__(__name, __old)
                raise
