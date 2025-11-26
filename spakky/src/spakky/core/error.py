from abc import ABC


class AbstractSpakkyFrameworkError(Exception, ABC):
    """Base class for all Spakky framework errors."""

    message: str
    """A human-readable message describing the error."""

    def __str__(self) -> str:
        """Return the error message."""
        return self.message
