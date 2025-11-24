"""Plugin initialization for Typer CLI integration.

Registers post-processor for automatic CLI command registration from
@CliController decorated classes.
"""

from spakky.application.application import SpakkyApplication

from spakky_typer.post_processor import TyperCLIPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Typer CLI plugin.

    Registers the post-processor for automatic CLI command registration.
    This function is called automatically by the Spakky framework during
    plugin loading.

    Args:
        app: The Spakky application instance.
    """
    app.add(TyperCLIPostProcessor)
