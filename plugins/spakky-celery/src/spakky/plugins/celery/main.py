"""Plugin initialization entry point."""

from celery import Celery
from spakky.core.application.application import SpakkyApplication
from spakky.core.pod.annotations.pod import Pod

from spakky.plugins.celery.aspects.task_dispatch import (
    AsyncCeleryTaskDispatchAspect,
    CeleryTaskDispatchAspect,
)
from spakky.plugins.celery.common.config import CeleryConfig
from spakky.plugins.celery.post_processor import CeleryPostProcessor


def _has_celery_pod(app: SpakkyApplication) -> bool:
    """Return whether the application already registered a Celery Pod."""
    return any(
        pod.type_ is Celery or Celery in pod.base_types
        for pod in app.container.pods.values()
    )


@Pod(name="celery_app")
def celery_app(config: CeleryConfig) -> Celery:
    """Create the default Celery application managed by the plugin."""
    celery = Celery(
        main=config.app_name,
        broker=config.broker_url,
        backend=config.result_backend,
    )
    celery.conf.update(
        task_serializer=config.task_serializer.value,
        result_serializer=config.result_serializer.value,
        accept_content=[serializer.value for serializer in config.accept_content],
        timezone=config.timezone,
        enable_utc=config.enable_utc,
    )
    return celery


def initialize(app: SpakkyApplication) -> None:
    """Initialize the Celery plugin.

    Registers CeleryConfig, CeleryPostProcessor, and task dispatch aspects.

    Args:
        app: The SpakkyApplication instance.
    """
    if not _has_celery_pod(app):
        app.add(CeleryConfig)
        app.add(celery_app)
    app.add(CeleryPostProcessor)
    app.add(CeleryTaskDispatchAspect)
    app.add(AsyncCeleryTaskDispatchAspect)
