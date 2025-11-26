from abc import ABC


class AbstractSpakkyFrameworkError(Exception, ABC):
    """Base class for all Spakky framework errors.

    The error message can be defined in two ways:
    1. Class-level: Define `message` as a class attribute for a fixed message.
    2. Instance-level: Pass `message` to the constructor to override the class default.

    If neither is provided, the message will be an empty string.
    """

    message: str = ""
    """A human-readable message describing the error."""

    def __init__(self, message: str | None = None, *args: object) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message, *args)
