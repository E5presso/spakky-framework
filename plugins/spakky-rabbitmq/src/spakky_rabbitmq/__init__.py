"""RabbitMQ plugin for Spakky framework.

This plugin provides RabbitMQ integration for domain event publishing and
consuming with automatic event handler registration and background services.

Prepare for release.
"""

from spakky.application.plugin import Plugin

PLUGIN_NAME = Plugin(name="spakky-rabbitmq")
"""Plugin identifier for the RabbitMQ integration."""
