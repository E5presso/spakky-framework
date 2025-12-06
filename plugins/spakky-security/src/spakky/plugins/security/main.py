"""Plugin initialization for Security utilities.

This plugin provides cryptographic utilities, password hashing, JWT handling,
and other security-related functions. Currently, it does not require any
post-processors or Pod registrations as it provides standalone utility functions.
"""

from spakky.core.application.application import SpakkyApplication


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Security plugin.

    This plugin provides utility functions and does not require any
    Pod registration or post-processor setup at this time.

    Args:
        app: The Spakky application instance.
    """
    # Security plugin provides utility functions only
    # No pods or post-processors to register
    pass
