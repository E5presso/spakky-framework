from typing import cast
from uuid import UUID

from uuid_extensions import uuid7 as get_id


def uuid7() -> UUID:
    """Generate a UUID v7 (time-ordered) identifier."""
    return cast(UUID, get_id())
