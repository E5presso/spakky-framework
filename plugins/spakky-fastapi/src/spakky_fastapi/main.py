"""Plugin initialization for FastAPI integration.

Registers post-processors that enable automatic route registration and
built-in middleware injection for FastAPI applications.
"""

from spakky.application.application import SpakkyApplication

from spakky_fastapi.post_processors.add_builtin_middlewares import (
    AddBuiltInMiddlewaresPostProcessor,
)
from spakky_fastapi.post_processors.register_routes import RegisterRoutesPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the FastAPI plugin.

    Registers post-processors for automatic route registration and middleware
    injection. This function is called automatically by the Spakky framework
    during plugin loading.

    Args:
        app: The Spakky application instance.
    """
    app.add(AddBuiltInMiddlewaresPostProcessor)
    app.add(RegisterRoutesPostProcessor)
