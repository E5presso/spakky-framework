"""Typer CLI plugin for Spakky framework.

This plugin provides Typer integration for building command-line interfaces
with automatic command registration and async support.
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-typer")
"""Plugin identifier for the Typer CLI integration."""
# Release test
