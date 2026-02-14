"""Cascade options for SQLAlchemy ORM relationships."""

from enum import Flag, auto


class CascadeOption(Flag):
    """Cascade operations for ORM relationships.

    Use the `|` operator to combine multiple options. Maps to SQLAlchemy's
    cascade string format internally.

    Examples:
        >>> from spakky.plugins.sqlalchemy.orm.relationships import OneToMany
        >>> from spakky.plugins.sqlalchemy.orm.relationships.cascade import CascadeOption
        >>>
        >>> # Single option
        >>> OneToMany(cascade=CascadeOption.DELETE)
        >>>
        >>> # Multiple options with | operator
        >>> OneToMany(cascade=CascadeOption.SAVE_UPDATE | CascadeOption.MERGE)
        >>>
        >>> # All operations with orphan deletion (default)
        >>> OneToMany(cascade=CascadeOption.ALL | CascadeOption.DELETE_ORPHAN)
    """

    NONE = 0
    """No cascade operations."""

    SAVE_UPDATE = auto()
    """Cascade save and update operations to related objects."""

    MERGE = auto()
    """Cascade merge operations to related objects."""

    EXPUNGE = auto()
    """Cascade expunge operations to related objects."""

    DELETE = auto()
    """Cascade delete operations to related objects."""

    DELETE_ORPHAN = auto()
    """Delete related objects when they are removed from the collection."""

    REFRESH_EXPIRE = auto()
    """Cascade refresh and expire operations to related objects."""

    ALL = SAVE_UPDATE | MERGE | EXPUNGE | DELETE | REFRESH_EXPIRE
    """All cascade operations except delete-orphan."""

    ALL_DELETE_ORPHAN = ALL | DELETE_ORPHAN
    """All cascade operations including delete-orphan (most common for parent-child)."""

    def to_string(self) -> str:
        """Convert cascade options to SQLAlchemy cascade string format.

        Returns:
            Cascade string for SQLAlchemy (e.g., "save-update, merge, delete").
        """
        if self == CascadeOption.NONE:
            return "none"

        parts: list[str] = []

        # Check for ALL first (it's a combination)
        # Use bitwise & to check if flag is set
        if self & CascadeOption.ALL == CascadeOption.ALL:
            parts.append("all")
            # Only add delete-orphan if it's also set
            if self & CascadeOption.DELETE_ORPHAN:
                parts.append("delete-orphan")
        else:
            # Check individual flags
            if self & CascadeOption.SAVE_UPDATE:
                parts.append("save-update")
            if self & CascadeOption.MERGE:
                parts.append("merge")
            if self & CascadeOption.EXPUNGE:
                parts.append("expunge")
            if self & CascadeOption.DELETE:
                parts.append("delete")
            if self & CascadeOption.REFRESH_EXPIRE:
                parts.append("refresh-expire")
            if self & CascadeOption.DELETE_ORPHAN:
                parts.append("delete-orphan")

        return ", ".join(parts) if parts else "none"

    @classmethod
    def from_string(cls, cascade_str: str) -> "CascadeOption":
        """Parse a SQLAlchemy cascade string to CascadeOption.

        Args:
            cascade_str: Cascade string (e.g., "all, delete-orphan").

        Returns:
            CascadeOption flag combination.
        """
        if cascade_str == "none":
            return cls.NONE

        result = cls.NONE
        parts = [p.strip() for p in cascade_str.split(",")]

        mapping = {
            "all": cls.ALL,
            "save-update": cls.SAVE_UPDATE,
            "merge": cls.MERGE,
            "expunge": cls.EXPUNGE,
            "delete": cls.DELETE,
            "delete-orphan": cls.DELETE_ORPHAN,
            "refresh-expire": cls.REFRESH_EXPIRE,
        }

        for part in parts:
            if part in mapping:
                result |= mapping[part]

        return result
