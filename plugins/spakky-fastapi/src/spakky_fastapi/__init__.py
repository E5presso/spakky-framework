"""FastAPI plugin for Spakky framework.

This plugin provides FastAPI integration with automatic route registration,
middleware support, and controller stereotypes for building REST APIs.
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-fastapi")
"""Plugin identifier for the FastAPI integration."""
# Release test
