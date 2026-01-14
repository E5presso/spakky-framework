from typing import cast
from uuid import UUID

from uuid_extensions import uuid7 as get_id


def uuid7() -> UUID:
    return cast(UUID, get_id())
