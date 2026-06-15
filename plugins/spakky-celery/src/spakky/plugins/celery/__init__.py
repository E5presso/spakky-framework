"""Package module."""

from spakky.core.application.plugin import Plugin
from spakky.plugins.celery.main import celery_app

PLUGIN_NAME = Plugin(name="spakky-celery")
"""Plugin identifier for the Celery plugin."""

__all__ = [
    "PLUGIN_NAME",
    "celery_app",
]
