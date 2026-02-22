"""User domain model for testing."""

from typing import Self
from uuid import UUID

from spakky.core.common.mutability import mutable
from spakky.core.utils.uuid import uuid7
from spakky.domain.models.entity import AbstractEntity


@mutable
class User(AbstractEntity[UUID]):
    """User domain entity for testing purposes."""

    username: str
    """Unique username for the user."""

    email: str
    """User's email address."""

    password_hash: str
    """Hashed password for authentication."""

    @classmethod
    def next_id(cls) -> UUID:
        """Generate next unique identifier for User entity.

        Returns:
            New UUID7 identifier.
        """
        return uuid7()

    def validate(self) -> None:
        """Validate user entity state.

        This is a test entity, so validation is minimal.
        """
        return

    @classmethod
    def create(
        cls,
        username: str,
        email: str,
        password_hash: str,
    ) -> Self:
        """Factory method to create a new User.

        Args:
            username: Unique username.
            email: User's email address.
            password_hash: Hashed password.

        Returns:
            New User instance.
        """
        return cls(
            uid=cls.next_id(),
            username=username,
            email=email,
            password_hash=password_hash,
        )
