from abc import ABC


class AbstractSpakkyFrameworkError(Exception, ABC):
    """Base class for all Spakky framework errors."""

    message: str
    """A human-readable message describing the error."""

    def __init__(self, message: str) -> None:
        self.message = message
