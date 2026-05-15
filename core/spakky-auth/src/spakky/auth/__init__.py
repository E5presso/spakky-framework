"""Provider-neutral authentication and authorization package root."""

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-auth")
"""Plugin identifier for the Spakky Auth package."""

__all__ = ["PLUGIN_NAME"]
