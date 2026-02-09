"""Binary field metadata for SQLAlchemy ORM."""

from spakky.core.common.mutability import mutable

from spakky.plugins.sqlalchemy.orm.fields.base import AbstractField


@mutable
class Binary(AbstractField[bytes]):
    """Metadata annotation for binary fields.

    Maps to SQLAlchemy's LargeBinary type. Stores binary data.

    Examples:
        >>> from typing import Annotated
        >>> from spakky.plugins.sqlalchemy.orm.fields.binary import Binary
        >>>
        >>> class Document:
        ...     file_data: Annotated[bytes, Binary(length=1024*1024)]  # 1MB
        ...     thumbnail: Annotated[bytes, Binary()]
    """

    length: int | None = None
    """Maximum length of binary data in bytes."""
