"""Plugin initialization for FastAPI integration.

Registers post-processors that enable automatic route registration and
built-in middleware injection for FastAPI applications.
"""

from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod

from fastapi import FastAPI

from spakky.plugins.fastapi.actuator import FastAPIActuatorConfig
from spakky.plugins.fastapi.config import FastAPIConfig
from spakky.plugins.fastapi.post_processors.add_builtin_middlewares import (
    AddBuiltInMiddlewaresPostProcessor,
)
from spakky.plugins.fastapi.post_processors.bind_lifespan import (
    BindLifespanPostProcessor,
)
from spakky.plugins.fastapi.post_processors.register_actuator import (
    RegisterActuatorPostProcessor,
)
from spakky.plugins.fastapi.post_processors.register_routes import (
    RegisterRoutesPostProcessor,
)


def _has_fastapi_pod(app: SpakkyApplication) -> bool:
    """Return whether the application already registered a FastAPI Pod."""
    return any(
        pod.type_ is FastAPI or FastAPI in pod.base_types
        for pod in app.container.pods.values()
    )


@Pod(name="fastapi_app")
def fastapi_app(config: FastAPIConfig) -> FastAPI:
    """Create the default FastAPI application managed by the plugin."""
    return FastAPI(
        title=config.title,
        description=config.description,
        version=config.version,
        debug=config.debug,
    )


def initialize(app: SpakkyApplication) -> None:
    """Initialize the FastAPI plugin.

    Registers post-processors for automatic route registration and middleware
    injection. This function is called automatically by the Spakky framework
    during plugin loading.

    Args:
        app: The Spakky application instance.
    """
    app.add(FastAPIConfig)
    if not _has_fastapi_pod(app):
        app.add(fastapi_app)
    app.add(FastAPIActuatorConfig)
    app.add(BindLifespanPostProcessor)
    app.add(AddBuiltInMiddlewaresPostProcessor)
    app.add(RegisterActuatorPostProcessor)
    app.add(RegisterRoutesPostProcessor)
