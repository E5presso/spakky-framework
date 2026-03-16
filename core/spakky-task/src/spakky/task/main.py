"""Plugin initialization entry point."""

from spakky.core.application.application import SpakkyApplication

from spakky.task.post_processor import TaskRegistrationPostProcessor


def initialize(app: SpakkyApplication) -> None:
    """Initialize the spakky-task plugin.

    Args:
        app: The SpakkyApplication instance.
    """
    app.add(TaskRegistrationPostProcessor)
