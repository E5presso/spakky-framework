"""Plugin initialization for Typer CLI integration.

Registers post-processor for automatic CLI command registration from
@CliController decorated classes.
"""

from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod
from typer import Typer

from spakky.plugins.typer.actuator import (
    ActuatorTyperCommandPostProcessor,
    ActuatorTyperConfig,
)
from spakky.plugins.typer.post_processor import TyperCLIPostProcessor


def _has_typer_pod(app: SpakkyApplication) -> bool:
    """Return whether the application already registered a Typer Pod."""
    return any(
        pod.type_ is Typer or Typer in pod.base_types
        for pod in app.container.pods.values()
    )


@Pod(name="typer_app")
def typer_app() -> Typer:
    """Create the default Typer application managed by the plugin."""
    return Typer()


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Typer CLI plugin.

    Registers the post-processor for automatic CLI command registration.
    This function is called automatically by the Spakky framework during
    plugin loading.

    Args:
        app: The Spakky application instance.
    """
    if not _has_typer_pod(app):
        app.add(typer_app)
    app.add(ActuatorTyperConfig)
    app.add(ActuatorTyperCommandPostProcessor)
    app.add(TyperCLIPostProcessor)
