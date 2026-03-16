"""Shared constants for the spakky-celery plugin."""

CELERY_TASK_CONTEXT_KEY: str = "__celery_task__"
"""ApplicationContext key indicating current execution is inside a Celery task."""
