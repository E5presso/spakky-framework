"""OAuth 2.0 client plugin identity."""

from spakky.core.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-oauth")
"""Plugin identifier for the OAuth 2.0 client package."""

__all__ = ["PLUGIN_NAME"]
