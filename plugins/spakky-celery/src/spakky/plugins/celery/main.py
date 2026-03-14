"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.plugins.celery.aspects.task_dispatch import (
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.common.config import CeleryConfig
from spakky.plugins.celery.post_processor import CeleryPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Celery plugin.

    Registers CeleryConfig, CeleryPostProcessor, and task dispatch aspects.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(CeleryConfig)
    app.add(CeleryPostProcessor)
    app.add(CeleryTaskDispatchAspect)
    app.add(AsyncCeleryTaskDispatchAspect)
